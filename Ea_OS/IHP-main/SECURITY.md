# Security and Threat Model

## Assumptions
- K_master custody is enforced by an HSM/KMS or pre-provisioned secret management; plaintext master bytes never leave hardware in production.
- Capsules are transported over authenticated channels; this library focuses on payload confidentiality and integrity.
- Hosts are bound to a `ServerEnvironmentProfile` (SEP) fingerprint; SEP hash anchors profile key derivation.

## Threat model
- **Mitigated**: nonce reuse/collisions (managed by `NonceManager`), AEAD for confidentiality/integrity, HKDF domain separation via labeled `CryptoSuite`, constant-time comparisons for capsule integrity checks, zeroization of derived keys on drop.
- **Not mitigated**: side-channel attacks outside constant-time comparisons, compromise of SEP capture process, malicious time sources, or hardware backdoors in HSM/KMS.

## Key rotation and hygiene
- Rotate `K_master` via your HSM/KMS and restart services with a fresh `KeyProvider` instance.
- Profile/session keys are derived per request and zeroized on drop; avoid logging secrets.
- Use `compute_server_env_hash_checked` to enforce SEP bounds before hashing.

## Secret Exposure Points

The library uses `expose()` methods to access secret material for cryptographic operations. All exposure points are audited and documented:

### Key Exposure Points

1. **Master Key** (`src/lib.rs:704`):
   - Used in `derive_profile_key_inner()` for HKDF expansion
   - Exposed bytes passed directly to `HKDF::new()` as IKM
   - Never copied, logged, or serialized

2. **Profile Key** (`src/lib.rs:726`):
   - Used in `derive_session_key_inner()` for HKDF expansion
   - Exposed bytes passed directly to `HKDF::new()` as salt
   - Never copied, logged, or serialized

3. **Session Key** (`src/lib.rs:909`):
   - Used in `select_cipher()` to initialize AES-GCM cipher
   - Exposed bytes copied internally by `Aes256Gcm::new_from_slice()`
   - Reference does not outlive function call

4. **Nonce** (`src/lib.rs:922, 942`):
   - Used in `encrypt_inner()` and `decrypt_inner()` for AEAD operations
   - Exposed bytes copied by `AesNonce::from_slice()`
   - Nonces are not secret material, but handled securely

### Test-Only Exposure

- `src/lib.rs:1470, 1485, 1557, 1558`: Test assertions only, not used in production code

### Safety Guarantees

- All `expose()` methods are `pub(crate)`, limiting access to internal modules
- All call sites include `// SAFETY:` comments documenting usage
- No exposure points log or serialize secret material
- Zeroize ensures secrets are cleared on drop
- References never outlive the containing function

## Review checklist
- Ensure `IhpConfig` bounds (timestamp drift, payload/fingerprint sizes) are validated and aligned with deployment policy.
- Confirm `observability` feature is disabled for ultra-high-sensitivity builds if tracing backends are untrusted.
- Verify compatibility tests (`validate_against_golden`) cover all supported protocol versions before upgrades.
- Audit all `expose()` call sites when modifying cryptographic code paths.

## Incident response
- Revoke affected profile/session material by rotating `K_master` and redeploying nodes with new SEPs.
- Inspect observability counters for version mismatches and timestamp skew anomalies to detect downgrade/replay attempts.
- Capture and rotate affected capsules if AEAD verification failures spike.
