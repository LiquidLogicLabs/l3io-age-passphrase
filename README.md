# l3io-age-passphrase

Streaming **age** encryption and decryption under a passphrase for Python 3.11+.

Output is a standard age v1 file with a **sole scrypt recipient**. Operators
recover plaintext with stock `age -d` (interactive passphrase prompt). This
package exists because [`pyrage`](https://github.com/woodruffw/pyrage) streams
recipient mode but only buffers passphrase payloads
([pyrage#172](https://github.com/woodruffw/pyrage/issues/172)).

Used by [`l3io-wordpress-database`](https://github.com/LiquidLogicLabs/l3io-wordpress-database)
for multi-GB dump/archive encryption.

## Install

Wheels are published on **GitHub Releases** (not PyPI yet).

```shell
# Example: Linux x86_64 manylinux abi3 wheel from the latest release
uv pip install \
  "https://github.com/LiquidLogicLabs/l3io-age-passphrase/releases/download/v0.1.0/l3io_age_passphrase-0.1.0-cp311-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
```

Or pin from a release asset URL in `[tool.uv.sources]` / a Dockerfile `ADD`.
Prefer the wheel that matches your platform (manylinux, musllinux, macOS, Windows).

From a local checkout (developers):

```shell
uv sync --group dev
make develop   # maturin develop --release
make test
```

## API

```python
from l3io_age_passphrase import encrypt, decrypt, encrypt_io, decrypt_io

# One-shot (small payloads)
ciphertext = encrypt(b"secret data", "passphrase")
plaintext = decrypt(ciphertext, "passphrase")

# Streaming (multi-GB dumps/archives) — bounded memory
encrypt_io(reader, writer, "passphrase")          # armored=False by default
decrypt_io(reader, writer, "passphrase")

# ASCII armor when you need a text-safe envelope
encrypt_io(reader, writer, "passphrase", armored=True)
```

Exceptions:

| Type | When |
|---|---|
| `EncryptError` | encryption or I/O failure while writing ciphertext |
| `DecryptError` | wrong passphrase, truncated/damaged stream, or non-age input |

Passphrases are never included in exception messages.

## Interop

| Producer | Consumer |
|---|---|
| this package | `age -d` (TTY passphrase) |
| this package | `age -d -j batchpass` + `AGE_PASSPHRASE_FD` |
| `age -e -j batchpass` | `decrypt` / `decrypt_io` |

Recipient / SSH encryption is out of scope — use `pyrage` for those.

## Backend choice in l3io-wordpress-database

That package selects backends with `L3IO_AGE_PASSPHRASE_BACKEND`:

- `auto` (default) — this binder if importable, else `age` + `age-plugin-batchpass`
- `binder` — require this package
- `cli` — require FiloSottile age ≥1.3 with the batchpass plugin

## Development

```shell
make check     # ruff + pytest
make build     # wheels into dist/
```

Requires Rust stable, Python ≥3.11, [uv](https://docs.astral.sh/uv/) 0.11.6,
and [maturin](https://www.maturin.rs/).

## Releasing

```shell
gh workflow run release.yml -f bump=patch   # or minor / major
```

That tags `vX.Y.Z`, builds multi-platform wheels, and attaches them to a
GitHub Release. PyPI publish is intentionally not wired yet.

## License

MIT. Built on the Rust [`age`](https://crates.io/crates/age) crate (MIT OR Apache-2.0).
