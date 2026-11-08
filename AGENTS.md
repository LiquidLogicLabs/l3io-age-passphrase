# l3io-age-passphrase

Streaming age passphrase bindings (PyO3). Consumed by `l3io-wordpress-database`
via the `encryption` extra. Python 3.11+, uv, maturin, ruff, pytest.

## Owner rule — CI and releases (Shawn, 2026-11-08)

Family-wide:

1. Work is not done until GitHub CI is completely green: every job and every
   matrix leg.
2. Before any release, tag, or publish, run `make preflight` for that commit.
   It runs `make check`, then everything act can: linux legs of `ci.yml`
   (ruff, clippy, ubuntu × every declared Python), plus dry-runs of
   `release.yml` / `publish.yml`.
3. Never release or publish while CI is red. **Release only through
   `make release`**, which refuses without a preflight stamp for HEAD and
   without every GitHub run for HEAD's full SHA completed as `success`.

### What act can and cannot run

- **act runs:** `ci.yml` linux jobs — `ruff`, `clippy`, and
  `test · ubuntu-latest · py3.11..3.13` (full Python axis; `--matrix os:ubuntu-latest`).
- **GitHub-only (named, not skipped silently):**
  - `test · macos-latest · …` (no macOS under act);
  - `release.yml` and `publish.yml` (tags, multi-arch wheels, registry tokens;
    dry-run with `make ci-dryrun`).

`vars.LOCAL_ACT` must not narrow the Python axis.
