# IHP Release Process

This document describes the release process for IHP, including versioning policy, release checklist, and procedures.

## Versioning Policy

IHP follows [Semantic Versioning](https://semver.org/) (SemVer):

- **MAJOR** version (X.0.0): Incompatible API changes or breaking protocol changes
- **MINOR** version (0.X.0): New functionality in a backwards-compatible manner
- **PATCH** version (0.0.X): Backwards-compatible bug fixes

### Current Status

- **Current version**: 0.1.0 (pre-release)
- **Target for 1.0.0**: After independent cryptographic review and remediation of findings

### Version Roadmap

- **0.1.0** → **0.2.0**: Post-crypto-review fixes, CI improvements, documentation
- **0.2.0** → **0.3.0**: Additional features, performance improvements
- **0.x.0** → **1.0.0**: Production-ready, stable API, comprehensive test coverage

## Release Checklist

Before creating a release, ensure all items are completed:

### Pre-Release

- [ ] All CI checks pass (formatting, linting, tests, audit)
- [ ] Security audit shows no high/critical vulnerabilities (`cargo audit`)
- [ ] All tests pass (unit, integration, golden fixtures)
- [ ] Golden fixtures validate (`cargo test --test fixture_check`)
- [ ] Documentation is up to date (README, SECURITY, RUNBOOK)
- [ ] CHANGELOG.md is updated with release notes
- [ ] Version number updated in `Cargo.toml`

### Build and Test

- [ ] Release build succeeds: `cargo build --release`
- [ ] Release build tests pass: `cargo test --release`
- [ ] Observability feature builds: `cargo build --features observability --release`
- [ ] Examples compile and run: `cargo run --example observability_demo --features observability`

### Security

- [ ] Security audit passed: `cargo audit`
- [ ] No high/critical vulnerabilities (or documented mitigations)
- [ ] Secret exposure points reviewed (if crypto code changed)
- [ ] Cryptographic review completed (for major releases)

### Documentation

- [ ] README.md reflects current features
- [ ] SECURITY.md is up to date
- [ ] RUNBOOK.md includes latest operational procedures
- [ ] CONTRIBUTING.md is current
- [ ] API documentation builds: `cargo doc --no-deps`

### Release Artifacts

- [ ] Git tag created: `git tag -a v0.1.0 -m "Release v0.1.0"`
- [ ] Release notes prepared (from CHANGELOG.md)
- [ ] GitHub release created (if publishing)
- [ ] Artifacts signed (if applicable)

## Release Procedure

### 1. Prepare Release Branch

```bash
# Ensure main branch is up to date
git checkout main
git pull origin main

# Create release branch
git checkout -b release/v0.1.0
```

### 2. Update Version

Update version in `Cargo.toml`:
```toml
[package]
version = "0.1.0"  # Update to new version
```

### 3. Update CHANGELOG

Add release notes to `CHANGELOG.md`:
```markdown
## [0.1.0] - 2024-01-15

### Added
- Initial release
- Core encryption/decryption functionality
- Observability support
```

### 4. Run Release Checklist

Execute all items in the release checklist above.

### 5. Create Release Commit

```bash
git add Cargo.toml CHANGELOG.md
git commit -m "chore: release v0.1.0"
```

### 6. Create Tag

```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin release/v0.1.0
git push origin v0.1.0
```

### 7. Create GitHub Release

1. Go to GitHub Releases page
2. Click "Draft a new release"
3. Select the tag `v0.1.0`
4. Copy release notes from CHANGELOG.md
5. Mark as "Latest release" (if this is the latest)
6. Publish release

### 8. Merge to Main

```bash
git checkout main
git merge release/v0.1.0
git push origin main
```

### 9. Publish to crates.io (if applicable)

```bash
# Ensure you're logged in
cargo login <token>

# Dry run first
cargo publish --dry-run

# Publish
cargo publish
```

**Note**: Publishing to crates.io requires:
- Valid LICENSE file (Apache-2.0)
- Repository URL in Cargo.toml
- Documentation URL in Cargo.toml
- No high/critical security vulnerabilities

## Hotfix Procedure

For critical bug fixes on released versions:

1. Checkout the release tag: `git checkout v0.1.0`
2. Create hotfix branch: `git checkout -b hotfix/v0.1.1`
3. Apply fix and test
4. Update version to patch increment (0.1.0 → 0.1.1)
5. Update CHANGELOG.md
6. Follow release procedure above
7. Merge hotfix back to main

## Post-Release

After release:

- [ ] Monitor metrics for issues
- [ ] Watch for security advisories
- [ ] Update documentation if needed
- [ ] Plan next release

## Release Signing (Optional)

To sign releases with GPG:

```bash
# Configure GPG
git config user.signingkey <your-gpg-key-id>

# Sign tag
git tag -s v0.1.0 -m "Release v0.1.0"

# Verify signature
git tag -v v0.1.0
```

## Emergency Releases

For security-critical fixes:

1. **Immediate**: Create hotfix branch and apply fix
2. **Fast-track**: Skip non-critical checklist items
3. **Security**: Ensure security audit passes
4. **Communication**: Notify users of security release
5. **Documentation**: Update SECURITY.md with advisory

## Version Compatibility

### Protocol Versions

- Protocol version changes require MAJOR version bump
- Multiple protocol versions can be supported simultaneously via `allowed_versions` in `IhpConfig`

### API Compatibility

- Public API changes require version bump per SemVer
- Internal APIs (`pub(crate)`) can change in MINOR versions
- Breaking changes to `IhpConfig`, `KeyProvider`, or core types require MAJOR bump

## Release Notes Template

```markdown
## [VERSION] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes to existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security fixes and advisories
```
