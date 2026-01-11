# IHP Operations Runbook

## Key rotation
- Rotate `K_master` in the HSM/KMS.
- Redeploy services with an `HsmKeyProvider` pointed at the new key alias/version.
- Validate with `golden_capsules()` to ensure wire-compat remains stable after rollout.

## Profile lifecycle
- Generate new `ServerProfileId` values per host via provisioning.
- Capture `ServerEnvironmentProfile` fingerprints at boot; validate lengths via `compute_server_env_hash_checked` before hashing.
- Persist `ServerEnvHash` alongside node metadata for audit.

## Drift tuning
- Configure `max_timestamp_drift` on `IhpConfig` (builder) per environment. Reject negative values; production defaults to 5 minutes.
- Monitor `ihp_timestamp_skew_seconds` histogram (when `observability` feature is enabled) to inform drift adjustments.

## Monitoring and observability
- Enable the `observability` feature to collect tracing spans for key derivation and encrypt/decrypt paths.
- Export `metrics` counters/histograms to Prometheus or OpenTelemetry:
  - `ihp_encrypt_success_total`, `ihp_decrypt_success_total`
  - `ihp_header_mismatch_total`, `ihp_version_mismatch_total`
  - `ihp_timestamp_skew_seconds`
- Trace contexts deliberately exclude secret material.

## Incident response
- On suspicious activity (tag failures, version mismatches), rotate `K_master` and invalidate affected SEPs.
- Force regeneration of session keys by rotating TLS exporter material and nonces.
- Use compatibility fixtures to confirm that remediation changes do not break legacy clients.

## HSM/KMS integrations
- Wrap master key access with `HsmKeyProvider`; derive profile/session keys in hardware when possible.
- Avoid exposing raw bytes; rely on `SecretKey::with_bytes` closures when local processing is required.

## Testing and fuzzing
- Unit tests cover validation boundaries, compatibility fixtures, and zeroization semantics.
- Property tests (proptest) exercise encrypt/decrypt idempotence and tamper detection.
- Fuzz harness stubs target ciphertext/nonce mutation (see `fuzz_targets/` placeholders for integration with `cargo fuzz`).
