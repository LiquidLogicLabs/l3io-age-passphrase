# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] — 2026-11-03

### Added

- Linux `armv7` manylinux and musllinux wheels (alongside existing x86_64 and
  aarch64), matching the official `wordpress` image arches we install into
  without a local Rust toolchain.
- Optional TestPyPI / PyPI publish targets on the Publish workflow (dispatch
  only; tags still only cut the GitHub Release + family-index mirror).

## [0.1.0] — 2026-10-26

### Added

- Streaming `encrypt_io` / `decrypt_io` for age passphrase (sole scrypt recipient).
- One-shot `encrypt` / `decrypt` helpers.
- Optional ASCII armor on encrypt paths.
- Stock `age -d` / `age -e -j batchpass` interoperability.
- Typed stubs (`l3io_age_passphrase.pyi`) and `py.typed`.

[0.1.1]: https://github.com/LiquidLogicLabs/l3io-age-passphrase/releases/tag/v0.1.1
[0.1.0]: https://github.com/LiquidLogicLabs/l3io-age-passphrase/releases/tag/v0.1.0
