# Contributing to IHP

Thank you for your interest in contributing to IHP! This document outlines the process for contributing code, documentation, and other improvements to the project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and professional environment for all contributors.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/your-username/IHP.git`
3. Create a branch: `git checkout -b fix/your-feature-name` or `feat/your-feature-name`
4. Make your changes
5. Test your changes: `cargo test` and `cargo clippy -- -D warnings`
6. Format your code: `cargo fmt --all`
7. Commit your changes with a clear message
8. Push to your fork: `git push origin fix/your-feature-name`
9. Open a Pull Request

## Branch Naming

Use descriptive branch names with prefixes:
- `fix/` - Bug fixes
- `feat/` - New features
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test additions or changes
- `ci/` - CI/CD changes

Examples:
- `fix/nonce-tracking`
- `feat/add-observability-example`
- `docs/update-runbook`

## Pull Request Process

### Before Submitting

1. **Ensure CI passes**: All GitHub Actions checks must pass before your PR can be merged
   - Formatting check (`cargo fmt --all -- --check`)
   - Linting check (`cargo clippy -- -D warnings`)
   - Tests (`cargo test`)
   - Security audit (`cargo audit`)

2. **Run tests locally**:
   ```bash
   cargo test
   cargo test --features observability
   cargo fmt --all -- --check
   cargo clippy -- -D warnings
   ```

3. **Update documentation**: If your changes affect user-facing APIs or behavior, update the relevant documentation

4. **Check golden fixtures**: If you modify the protocol or serialization format, ensure golden fixtures still validate:
   ```bash
   cargo test --test fixture_check
   ```

### PR Requirements

- **Title**: Use a clear, descriptive title (e.g., "fix: normalize Cargo.toml and fix Rust edition")
- **Description**: Explain what changes you made and why
- **Tests**: Include tests for new functionality
- **Documentation**: Update relevant docs (README, SECURITY.md, RUNBOOK.md, etc.)
- **CI**: All CI checks must pass
- **Review**: At least one code owner must approve (see CODEOWNERS)

### Required Checks

The following checks must pass before a PR can be merged:

- ✅ Formatting (`cargo fmt`)
- ✅ Linting (`cargo clippy`)
- ✅ Tests (with and without `observability` feature)
- ✅ Security audit (`cargo audit`)
- ✅ Golden fixture validation (if protocol changes)

## Code Ownership

See [`.github/CODEOWNERS`](.github/CODEOWNERS) for details on which files require approval from specific teams:

- **Cryptographic code** (`src/lib.rs`, `src/server.rs`, `src/client.rs`) requires crypto reviewer approval
- **CI/CD workflows** require CI engineer approval
- **Dependency changes** (`Cargo.toml`, `Cargo.lock`) require release manager approval
- **Security documentation** requires security team review

## Coding Standards

### Rust Style

- Follow standard Rust formatting (`cargo fmt`)
- Address all clippy warnings (`cargo clippy -- -D warnings`)
- Use `#![forbid(unsafe_code)]` - no unsafe code allowed
- Prefer explicit error handling over panics
- Document public APIs with doc comments

### Security Considerations

- **Never log or expose secret material**: Use `zeroize` for sensitive data
- **Use constant-time comparisons**: For secret comparisons, use `constant_time_equal`
- **Audit `expose()` calls**: Document all uses of `expose()` methods
- **Validate inputs**: Check bounds and validate all user inputs
- **Nonce handling**: Ensure nonces are unique and properly tracked

### Testing

- Write unit tests for new functionality
- Include property tests (`proptest`) for cryptographic operations
- Test both with and without the `observability` feature
- Ensure golden fixtures validate after protocol changes

## Cryptographic Changes

**CRITICAL**: Changes to cryptographic primitives, key derivation, or protocol format require:

1. **Independent cryptographic review** (external or senior crypto engineer)
2. **Updated golden fixtures** if protocol changes
3. **Comprehensive test coverage** including known-answer tests (KATs)
4. **Security documentation updates** in SECURITY.md

Do not modify cryptographic algorithms or protocol formats without explicit approval from the crypto review team.

## Documentation

- Update `README.md` for user-facing changes
- Update `SECURITY.md` for security-related changes
- Update `RUNBOOK.md` for operational changes
- Add doc comments for public APIs
- Include examples for new features

## Release Process

See [RELEASE.md](RELEASE.md) for details on the release process. In general:

- Version numbers follow semantic versioning
- Releases require all CI checks to pass
- Security audit must show no high/critical vulnerabilities
- Golden fixtures must validate
- CHANGELOG.md must be updated

## Questions?

If you have questions about contributing:

- Open an issue for discussion
- Check existing documentation (README.md, SECURITY.md, RUNBOOK.md)
- Review existing PRs for examples

Thank you for contributing to IHP!
