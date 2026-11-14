"""The scrypt work factor must not depend on how busy the host is.

age's ``scrypt::Recipient::new`` picks the encryption work factor, and
``scrypt::Identity::new`` the largest one decryption accepts (that target + 4),
by timing a small scrypt run on the wall clock. On a loaded host the timing
runs long, so a file encrypted while the host was idle (log_n 18-19 here) is
refused while it is busy ("Excessive work parameter"), and a file encrypted
while it is busy gets a weak work factor. A backup tool cannot have either.

Each test runs the binder in a child process that is throttled while it
works: for its first seconds it runs about 0.5 ms in every 100 ms, so every
wall-clock measurement it takes then is over a hundred times too long (log2:
about 7), whatever the host's speed or scheduler. Encryption and decryption
must not notice. The child's address space is capped at 2 GiB, so a binder
that would run scrypt beyond the maximum fails fast instead of taking 8 GiB.
"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import l3io_age_passphrase as age_pass

PASSPHRASE = "test-passphrase-not-a-secret"
PLAIN = b"work factor\n" * 100
#: The work factor the binder writes, stock ``age -p``'s.
WORK_FACTOR = 18
#: ``PLAIN`` as stock ``age -p`` (1.2.1) encrypted it with ``PASSPHRASE``: log_n 18.
STOCK_AGE = Path(__file__).parent / "data" / "stock-age-p-work-factor-18.age"
_STANZA = re.compile(rb"^-> scrypt \S+ (\d+)$", re.MULTILINE)

_CHILD = r"""
import io, resource, sys
import l3io_age_passphrase as age_pass
# Cap address space so an unfixed binder cannot spend 8 GiB on log_n 23.
# Best-effort: macOS often rejects RLIMIT_AS here ("current limit exceeds
# maximum limit"); the fixed max_work_factor still refuses before scrypt.
try:
    resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
except (ValueError, OSError, AttributeError):
    pass
mode, path, passphrase = sys.argv[1:4]
data = open(path, "rb").read()
sys.stdout.write("ready\n"); sys.stdout.flush()
sys.stdin.readline()
out = io.BytesIO()
try:
    if mode == "encrypt":
        age_pass.encrypt_io(io.BytesIO(data), out, passphrase)
    else:
        age_pass.decrypt_io(io.BytesIO(data), out, passphrase)
except age_pass.DecryptError as exc:
    sys.stdout.write("DecryptError: " + str(exc).replace("\n", " ") + "\n")
    sys.exit(3)
open(path + ".out", "wb").write(out.getvalue())
"""


def _throttled_run(mode: str, source: Path, *, seconds: float = 4.0) -> tuple[int, str]:
    """Run ``mode`` on ``source`` in a child stopped > 99% of the first ``seconds``."""
    child = subprocess.Popen(  # noqa: S603 - this interpreter, a fixed script
        [sys.executable, "-c", _CHILD, mode, str(source), PASSPHRASE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdin is not None and child.stdout is not None
    try:
        assert child.stdout.readline() == "ready\n"
        # Stopped before it is told to go, so it never runs unthrottled.
        os.kill(child.pid, signal.SIGSTOP)
        child.stdin.write("go\n")
        child.stdin.flush()
        end = time.monotonic() + seconds
        while time.monotonic() < end and child.poll() is None:
            # Runs about 0.5 ms (a SIGSTOP sent at once would cancel the
            # SIGCONT before the child ran at all) ...
            os.kill(child.pid, signal.SIGCONT)
            time.sleep(0.0005)
            os.kill(child.pid, signal.SIGSTOP)
            time.sleep(0.1)  # ... then waits 100 ms
    except ProcessLookupError:
        pass
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(child.pid, signal.SIGCONT)
    output, _ = child.communicate(timeout=120)
    return child.returncode, output


def _throttled(mode: str, source: Path) -> bytes:
    code, output = _throttled_run(mode, source)
    assert code == 0, output
    return Path(f"{source}.out").read_bytes()


def _work_factor(sealed: bytes) -> int:
    found = _STANZA.findall(sealed)
    assert len(found) == 1, found
    return int(found[0])


def test_encryption_uses_the_fixed_work_factor_on_a_busy_host(tmp_path: Path) -> None:
    source = tmp_path / "plain"
    source.write_bytes(PLAIN)
    sealed = _throttled("encrypt", source)
    assert _work_factor(sealed) == WORK_FACTOR
    assert age_pass.decrypt(sealed, PASSPHRASE) == PLAIN


def test_encryption_uses_the_fixed_work_factor_unthrottled() -> None:
    assert _work_factor(age_pass.encrypt(PLAIN, PASSPHRASE)) == WORK_FACTOR


def test_a_busy_host_decrypts_what_stock_age_encrypted(tmp_path: Path) -> None:
    sealed = STOCK_AGE.read_bytes()
    assert _work_factor(sealed) == WORK_FACTOR
    assert age_pass.decrypt(sealed, PASSPHRASE) == PLAIN
    source = tmp_path / "sealed.age"
    source.write_bytes(sealed)
    assert _throttled("decrypt", source) == PLAIN


def test_a_work_factor_above_the_maximum_is_refused(tmp_path: Path) -> None:
    sealed = STOCK_AGE.read_bytes()
    # 23 > the fixed maximum (22): refused before any scrypt work. Throttled,
    # so a binder without the fixed maximum refuses it too rather than
    # spending 8 GiB on scrypt (this guards the cap, not the regression).
    forged = sealed.replace(f" {_work_factor(sealed)}\n".encode(), b" 23\n", 1)
    assert _work_factor(forged) == 23
    source = tmp_path / "forged.age"
    source.write_bytes(forged)
    code, output = _throttled_run("decrypt", source)
    assert code == 3, output
    assert "Excessive work parameter" in output
