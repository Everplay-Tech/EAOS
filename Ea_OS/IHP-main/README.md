# IHP Capsule Library

This library implements an opinionated, hardened IHP capsule pipeline with zeroized secrets, deterministic protocol configuration, and observability hooks. All cryptographic operations are driven by [`IhpConfig`] and [`KeyProvider`] so that environments backed by HSM/KMS can avoid exposing master keys to process memory.

## Getting started

1. Add the crate to your `Cargo.toml`.
2. Construct an [`IhpConfig`] via the builder to set drift, allowed protocol versions, algorithm choices, and max lengths.
3. Implement a [`KeyProvider`] (e.g. `InMemoryKeyProvider` for tests or `HsmKeyProvider` for production) to supply derived profile and session keys.
4. Use `encrypt_capsule`/`decrypt_capsule` with typed inputs (`ClientNonce`, `BoundedPayload`, `CapsuleTimestamp`, `IhpNetworkContext`).

```rust
use ihp::*;
let config = IhpConfig::builder()
    .max_timestamp_drift(300)
    .build()?;
let sep = ServerEnvironmentProfile { /* ... */ };
let env_hash = compute_server_env_hash_checked(&sep, &config)?;
let provider = InMemoryKeyProvider::new(*b"master key material for ihp proto*");
let network = IhpNetworkContext { rtt_bucket: 7, path_hint: 120 };
let client_nonce = ClientNonce::new([7u8; 24]);
let k_profile = provider.profile_key(ServerProfileId(42), &env_hash, &config.crypto)?;
let k_session = provider.session_key(&k_profile, b"tls exporter key material", &client_nonce, &network, ServerProfileId(42), &config.crypto)?;
let capsule = encrypt_capsule(
    &config,
    99,
    client_nonce,
    ServerProfileId(42),
    network,
    env_hash,
    &k_session,
    &BoundedPayload::new(b"payload".to_vec(), config.max_plaintext_len)?,
    CapsuleTimestamp::new(1_700_000_000)?,
)?;
```

## Observability

Enable the `observability` feature to activate tracing spans and metrics. Metrics are emitted for encryption/decryption success, header/version mismatches, and timestamp skew histograms. Wire the `metrics` crate to Prometheus or OpenTelemetry exporters in your application.

### Setting up observability

1. **Enable the feature** in your `Cargo.toml`:
   ```toml
   [dependencies]
   ihp = { path = ".", features = ["observability"] }
   ```

2. **Initialize tracing** (for spans):
   ```rust
   use tracing_subscriber;
   
   tracing_subscriber::fmt()
       .with_max_level(tracing::Level::INFO)
       .init();
   ```

3. **Set up metrics** (for Prometheus):
   ```rust
   use metrics_exporter_prometheus::PrometheusBuilder;
   
   PrometheusBuilder::new()
       .install()
       .expect("failed to install Prometheus recorder");
   ```

4. **Run the demo**:
   ```bash
   cargo run --example observability_demo --features observability
   RUST_LOG=debug cargo run --example observability_demo --features observability
   ```

See `examples/observability_demo.rs` for a complete example.

### Local development

1. **Run tests**:
   ```bash
   cargo test
   cargo test --features observability
   ```

2. **Run integration tests**:
   ```bash
   cargo test --test http_server
   ```

3. **Check formatting and linting**:
   ```bash
   cargo fmt --all -- --check
   cargo clippy -- -D warnings
   ```

4. **Validate golden fixtures**:
   ```bash
   cargo test --test fixture_check
   # Or use the helper script:
   ./scripts/check_fixture.sh
   ```

5. **Run fuzz tests** (requires nightly):
   ```bash
   cd fuzz
   cargo fuzz run capsule_roundtrip
   ```

## Offline mirrors and CI

The repo ships a `.cargo/config.toml` that defines a `local-mirror` replacement for crates.io. CI and local builds stay online by default, but you can opt into an internal mirror or vendored cache when egress is blocked:

1. Populate a mirror:
   - Vendor dependencies: `cargo vendor --locked vendor/` to create a `vendor/` directory that can be cached by your CI artifact store.
   - Or point to an internal registry index: set `CARGO_MIRROR_REGISTRY="registry+https://artifactory.example.com/api/cargo/virtual/index"` (or a `registry+file:///...` URL for a mounted mirror).
2. Export mirror-aware environment for offline runs: `CARGO_NET_OFFLINE=1 CARGO_REGISTRIES_CRATES_IO_PROTOCOL=sparse`.
3. Run CI through the helper so it honors the mirror when present (but still works against crates.io when not): `./ci.sh` with either `CARGO_MIRROR_DIRECTORY=$(pwd)/vendor` or `CARGO_MIRROR_REGISTRY=registry+file://$(pwd)/vendor/index`.

## Compatibility fixtures

Wire-format fixtures live in `tests/fixtures/` (stored as hex text for VCS friendliness) and are loaded by `validate_against_golden` to protect serialization compatibility per protocol version. Regenerate fixtures with `cargo run --example gen_fixture` if protocol changes are intentionally accepted, and verify them locally with `scripts/check_fixture.sh` (which runs `cargo test --test fixture_check`). CI will fail if the regenerated capsule does not match `tests/fixtures/capsule_v1.hex`, signaling that a fixture refresh is required before landing the change.

## License

This project is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

## Docs and operations

- See [SECURITY.md](SECURITY.md) for threat model and review checklists.
- Operational playbooks (rotation, drift tuning, monitoring hooks) live in [`docs/RUNBOOK.md`](docs/RUNBOOK.md).
