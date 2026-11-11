"""A re-dispatch must not silently replace GitHub release wheels.

softprops/action-gh-release replaces same-named assets without comparing them.
publish.yml skips creation when the release exists, then checks each dist file's
sha256 against the release (upload missing without --clobber; fail on mismatch).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
PUBLISH_YML = WORKFLOWS / "publish.yml"
_RELEASE_ACTIONS = ("git-action-release@", "action-gh-release@")
_WHEEL = "l3io_age_passphrase-9.9.9-cp311-abi3-linux_x86_64.whl"
_SDIST = "l3io_age_passphrase-9.9.9.tar.gz"

_STUB_GH = """#!/usr/bin/env bash
set -eu
echo "$*" >> "$STUB_LOG"
case "$1 $2" in
  "release view") cat "$STUB_LISTING" ;;
  "release download")
    shift 3; name=""; dir=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --pattern) name=$2; shift 2 ;;
        --dir) dir=$2; shift 2 ;;
        *) shift ;;
      esac
    done
    cp "$STUB_ASSETS/$name" "$dir/$name" ;;
  "release upload") ;;
  *) echo "unexpected gh call: $*" >&2; exit 2 ;;
esac
"""


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _creates_a_release(step: dict) -> bool:
    uses = str(step.get("uses", ""))
    return any(a in uses for a in _RELEASE_ACTIONS) or "gh release create" in str(
        step.get("run", "")
    )


def _skip_flag(step: dict) -> str | None:
    with_ = step.get("with") or {}
    for key in ("skip-if-release-exists", "skip_if_exists"):
        if key in with_:
            return str(with_[key])
    return None


def _release_findings(doc: dict) -> list[str]:
    findings = []
    for job_id, job in (doc.get("jobs") or {}).items():
        steps = job.get("steps") or []
        for i, step in enumerate(steps):
            if not _creates_a_release(step):
                continue
            where = f"{job_id}: {step.get('uses') or step.get('name')}"
            if str(_skip_flag(step)).lower() != "true":
                findings.append(f"{where} does not skip when the release already exists")
            checks = [
                s
                for s in steps[i + 1 :]
                if "gh release view" in str(s.get("run", ""))
                and "gh release upload" in str(s.get("run", ""))
            ]
            if not checks:
                findings.append(f"{where} has no later step checking the assets")
            elif any("--clobber" in str(s.get("run", "")) for s in checks):
                findings.append(f"{where}: the asset check may overwrite (--clobber)")
    return findings


def _release_job(doc: dict) -> list[dict]:
    return doc["jobs"]["github-release"]["steps"]


def _creator(doc: dict) -> dict:
    return next(s for s in _release_job(doc) if _creates_a_release(s))


def _asset_step(doc: dict) -> dict:
    return next(s for s in _release_job(doc) if "gh release upload" in str(s.get("run", "")))


def test_there_is_a_release_step_to_check() -> None:
    assert any(
        _creates_a_release(s)
        for j in (_load(PUBLISH_YML).get("jobs") or {}).values()
        for s in j.get("steps") or []
    )


def test_every_release_step_tolerates_an_existing_release() -> None:
    assert _release_findings(_load(PUBLISH_YML)) == []


def test_the_release_rule_rejects_a_planted_violation() -> None:
    doc = _load(PUBLISH_YML)
    assert _release_findings(doc) == []
    _creator(doc)["with"].pop("skip_if_exists", None)
    assert _release_findings(doc)


def test_asset_check_clobber_is_caught() -> None:
    doc = _load(PUBLISH_YML)
    step = _asset_step(doc)
    step["run"] = step["run"].replace(
        'gh release upload "$TAG"', 'gh release upload --clobber "$TAG"'
    )
    assert _release_findings(doc)


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _run_asset_check(
    tmp_path: Path, release: dict[str, tuple[bytes, bool]]
) -> tuple[int, str, list[str]]:
    work = tmp_path / "work"
    (work / "dist").mkdir(parents=True)
    (work / "dist" / _WHEEL).write_bytes(b"wheel")
    (work / "dist" / _SDIST).write_bytes(b"sdist")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "gh").write_text(_STUB_GH, encoding="utf-8")
    (bin_ / "gh").chmod(0o755)
    assets = tmp_path / "assets"
    assets.mkdir()
    rows = []
    for name, (data, recorded) in release.items():
        (assets / name).write_bytes(data)
        rows.append(f"{name}\t{_digest(data) if recorded else ''}\n")
    (tmp_path / "listing").write_text("".join(rows), encoding="utf-8")
    log = tmp_path / "gh.log"
    log.touch()
    env = {
        **os.environ,
        "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}",
        "STUB_LOG": str(log),
        "STUB_LISTING": str(tmp_path / "listing"),
        "STUB_ASSETS": str(assets),
        "TAG": "v9.9.9",
    }
    proc = subprocess.run(  # noqa: S603
        ["bash", "-c", _asset_step(_load(PUBLISH_YML))["run"]],  # noqa: S607
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr, log.read_text().splitlines()


def _uploads(calls: list[str]) -> list[str]:
    return [c for c in calls if c.startswith("release upload")]


def test_the_asset_check_passes_a_release_that_already_has_this_build(tmp_path: Path) -> None:
    code, out, calls = _run_asset_check(
        tmp_path, {_WHEEL: (b"wheel", True), _SDIST: (b"sdist", True)}
    )
    assert code == 0, out
    assert _uploads(calls) == []


def test_the_asset_check_uploads_only_the_missing_name(tmp_path: Path) -> None:
    code, out, calls = _run_asset_check(tmp_path, {_WHEEL: (b"wheel", True)})
    assert code == 0, out
    assert _uploads(calls) == [f"release upload v9.9.9 dist/{_SDIST}"]


def test_the_asset_check_fails_on_different_content_and_uploads_nothing(tmp_path: Path) -> None:
    code, out, calls = _run_asset_check(tmp_path, {_WHEEL: (b"another build", True)})
    assert code != 0
    assert f"already has {_WHEEL}" in out
    assert _uploads(calls) == []
