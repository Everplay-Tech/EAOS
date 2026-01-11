# Changelog

All notable changes to IHP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive CI workflows with vendor support, security audit, and fuzzing
- CODEOWNERS and CONTRIBUTING.md for governance
- Observability demo example (`examples/observability_demo.rs`)
- Extended RUNBOOK.md with operational procedures (key rotation, emergency response, troubleshooting)
- Security documentation for `expose()` call sites in SECURITY.md
- Release process documentation (RELEASE.md)
- Golden fixture validation in CI

### Changed
- Fixed Rust edition from "2024" to "2021" (2024 doesn't exist yet)
- Fixed duplicate field in `ProfileResponse` struct
- Enhanced documentation with local development setup guide

### Security
- Audited and documented all `expose()` call sites with safety comments
- Added security review checklist for cryptographic code

## [0.1.0] - TBD

### Added
- Initial release
- Core IHP capsule encryption/decryption functionality
- HKDF-based key derivation (profile and session keys)
- AES-256-GCM AEAD encryption
- Zeroize integration for secret material
- Golden known-answer tests (KATs)
- Minimal Axum HTTP server (`/ihp/profile`, `/ihp/auth` endpoints)
- Observability support (tracing and metrics) via `observability` feature
- Fuzzing harness for capsule round-trip and nonce handling
- Property tests (proptest) for round-trip encryption
- Client helper utilities for capsule construction
- Server environment profile binding
- Timestamp drift validation
- Constant-time comparisons for integrity checks

### Security
- Zeroized secret keys and nonces
- Constant-time header ID comparison
- Domain separation via AAD construction
- HKDF domain separation via labeled crypto domains

[Unreleased]: https://github.com/Everplay-Tech/IHP/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Everplay-Tech/IHP/releases/tag/v0.1.0
