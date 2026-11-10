"""PyPI uploads must use trusted publishing (OIDC), not a long-lived token.

Passing ``password:`` to ``pypa/gh-action-pypi-publish`` disables trusted
publishing and attestations. TestPyPI may still use ``PYPI_TEST_TOKEN`` until a
publisher is registered there.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def pypi_org_uploads_with_credentials(workflows: Path) -> list[str]:
    bad: list[str] = []
    for workflow in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
        document = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for job_id, job in (document.get("jobs") or {}).items():
            for step in (job or {}).get("steps") or []:
                if not str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish"):
                    continue
                with_ = step.get("with") or {}
                target = str(with_.get("repository-url", ""))
                if "test.pypi.org" in target:
                    continue
                for key in ("user", "password"):
                    if key in with_:
                        bad.append(f"{workflow.name}:{job_id} passes {key}= to pypi.org")
    return bad


def test_pypi_org_upload_uses_trusted_publishing() -> None:
    assert WORKFLOWS.is_dir(), f"missing {WORKFLOWS}"
    assert pypi_org_uploads_with_credentials(WORKFLOWS) == []


def test_publish_pypi_job_requests_id_token() -> None:
    document = yaml.safe_load((WORKFLOWS / "publish.yml").read_text(encoding="utf-8")) or {}
    job = (document.get("jobs") or {}).get("publish-pypi") or {}
    perms = job.get("permissions") or {}
    assert perms.get("id-token") == "write", (
        "publish-pypi needs permissions.id-token: write for trusted publishing"
    )


def test_a_pypi_org_token_is_caught(tmp_path: Path) -> None:
    (tmp_path / "token.yml").write_text(
        "on: push\njobs:\n  up:\n    steps:\n"
        "      - uses: pypa/gh-action-pypi-publish@release/v1\n"
        "        with:\n"
        "          password: ${{ secrets.PYPI_TOKEN }}\n",
        encoding="utf-8",
    )
    assert pypi_org_uploads_with_credentials(tmp_path) == [
        "token.yml:up passes password= to pypi.org"
    ]
