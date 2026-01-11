# IHP Operational Runbook

## Key management

- **Master keys:** Provision `K_master` via HSM/KMS and inject using `MasterKeyProvider` or `InMemoryKeyProvider::from_hsm_wrapped`. Never log or serialize raw key bytes.
- **Profile keys:** Derive with `derive_profile_key` using the validated server environment hash. Rotate by updating `K_master` and invalidating cached derived keys; profile derivation is deterministic from master + SEP.
- **Session keys:** Derive with `derive_session_key` per TLS exporter material, client nonce, and network context. Sessions are ephemeral and zeroized on drop.

## Profile ID lifecycle

- Track `ServerProfileId` assignment per host profile; avoid reuse across unrelated SEPs.
- When hardware or OS fingerprints change, recompute the SEP and roll a new `ServerProfileId` if replay protection across profiles is required.

## Drift tuning

- Configure `max_timestamp_drift` via `IhpConfig::builder()`. Bounds are enforced (`MAX_ALLOWED_DRIFT_SECONDS`) to prevent unbounded acceptance windows.
- Monitor `ihp.drift.seconds` histogram to detect clock skew; tighten drift when skew stabilizes.

## Monitoring and telemetry

- Enable the `observability` feature to emit tracing spans and metrics.
- Key metrics:
  - `ihp.encrypt.success` / `ihp.encrypt.failure`
  - `ihp.encrypt.version_rejected`
  - `ihp.decrypt.success` / `ihp.decrypt.failure`
  - `ihp.decrypt.version_rejected`, `ihp.decrypt.header_mismatch`, `ihp.decrypt.drift_rejected`
  - `ihp.drift.seconds` histogram
- Export metrics via Prometheus/OpenTelemetry in the host application; avoid emitting sensitive material in spans.

## Key rotation procedure

### Planned rotation

1. **Prepare new master key:**
   - Generate new `K_master` in HSM/KMS
   - Store key material securely (HSM-backed preferred)
   - Document key ID and rotation timestamp

2. **Update key provider:**
   - Modify `MasterKeyProvider` implementation to return new key
   - Ensure old key remains accessible during transition period (if needed)
   - Test key derivation with new master key

3. **Deploy with new key:**
   - Deploy updated service binaries with new `MasterKeyProvider`
   - Monitor metrics for encryption/decryption success rates
   - Verify golden fixtures still validate (confirms no accidental protocol changes)

4. **Invalidate old sessions:**
   - Existing capsules encrypted with old profile keys will fail to decrypt
   - Clients must re-authenticate to obtain new capsules
   - Monitor for increased `ihp.decrypt.failure` metrics (expected during transition)

5. **Cleanup:**
   - After transition period, remove old key from HSM/KMS
   - Update documentation with new key rotation date
   - Archive old key material (if retention policy requires)

### Emergency rotation (key compromise)

1. **Immediate actions:**
   - Rotate `K_master` in HSM/KMS immediately
   - Deploy emergency binary with new key provider
   - Revoke all existing sessions/capsules

2. **Investigation:**
   - Review access logs for unauthorized key access
   - Check observability metrics for anomalies
   - Document scope of potential exposure

3. **Recovery:**
   - Force all clients to re-authenticate
   - Monitor for suspicious decryption attempts
   - Consider regenerating `ServerEnvHash` if server environment was compromised

## Emergency procedures

### Key compromise response

**Severity: CRITICAL**

1. **Containment (0-15 minutes):**
   - Rotate `K_master` immediately in HSM/KMS
   - Deploy emergency service update with new key
   - Enable additional logging/monitoring

2. **Assessment (15-60 minutes):**
   - Review recent access logs and metrics
   - Identify potential exposure window
   - Notify security team and stakeholders

3. **Remediation (1-4 hours):**
   - Force all clients to re-authenticate
   - Invalidate all existing capsules
   - Regenerate `ServerEnvHash` if server environment compromised
   - Update `IhpConfig` to reject old protocol versions if needed

4. **Post-incident (24-48 hours):**
   - Document incident timeline and root cause
   - Review and update key rotation procedures
   - Conduct post-mortem with security team

### Version rollback procedure

**Use case:** Need to rollback to previous protocol version due to compatibility issues

1. **Assess impact:**
   - Identify which clients/services depend on current version
   - Check if rollback breaks any integrations

2. **Update configuration:**
   - Modify `IhpConfig` to allow previous version:
     ```rust
     let mut allowed = HashSet::new();
     allowed.insert(ProtocolVersion::V1); // Add previous version
     let config = IhpConfig::builder()
         .allowed_versions(allowed)
         .build();
     ```

3. **Deploy rollback:**
   - Deploy service with updated `IhpConfig`
   - Monitor metrics for version acceptance
   - Verify clients can authenticate successfully

4. **Monitor:**
   - Watch `ihp.decrypt.version_rejected` metrics
   - Ensure no increase in authentication failures
   - Plan permanent fix for compatibility issue

### Service degradation response

**Symptoms:** Increased `ihp.decrypt.failure`, authentication timeouts

1. **Diagnose:**
   - Check `ihp.decrypt.failure` metrics by error code
   - Review `ihp.drift.seconds` histogram for clock skew
   - Check `ihp.decrypt.header_mismatch` for tampering attempts
   - Review server logs for errors

2. **Common causes:**
   - Clock skew: Adjust `max_timestamp_drift` if legitimate drift detected
   - Key mismatch: Verify `K_master` matches across all instances
   - Protocol version mismatch: Check `allowed_versions` configuration
   - Network issues: Review TLS exporter key derivation

3. **Remediation:**
   - Fix root cause (clock sync, key rotation, config update)
   - Restart affected services if needed
   - Monitor metrics for recovery

## Monitoring and alerting setup

### Required metrics

Enable the `observability` feature and export metrics to your monitoring system (Prometheus/OpenTelemetry):

**Key metrics to monitor:**
- `ihp.encrypt.success` / `ihp.encrypt.failure` - Encryption operation health
- `ihp.decrypt.success` / `ihp.decrypt.failure` - Decryption operation health
- `ihp.decrypt.version_rejected` - Protocol version mismatches
- `ihp.decrypt.header_mismatch` - Potential tampering attempts
- `ihp.decrypt.drift_rejected` - Clock skew issues
- `ihp.drift.seconds` (histogram) - Timestamp drift distribution

### Alert thresholds

**Critical alerts:**
- `ihp.decrypt.failure` rate > 10% for 5 minutes
- `ihp.decrypt.header_mismatch` > 5/minute (potential tampering)
- `ihp.decrypt.version_rejected` spike (version compatibility issue)

**Warning alerts:**
- `ihp.drift.seconds` p95 > 60 seconds (clock skew)
- `ihp.encrypt.failure` rate > 1% for 10 minutes
- Authentication latency p99 > 500ms

### Example Prometheus configuration

```yaml
groups:
  - name: ihp_alerts
    rules:
      - alert: IHPHighDecryptFailureRate
        expr: rate(ihp_decrypt_failure_total[5m]) / rate(ihp_decrypt_total[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "IHP decrypt failure rate exceeds 10%"
      
      - alert: IHPHeaderMismatchSpike
        expr: rate(ihp_decrypt_header_mismatch_total[1m]) > 5
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Potential tampering detected - header mismatches"
```

### Tracing setup

Enable tracing for debugging:

```rust
use tracing_subscriber;

tracing_subscriber::fmt()
    .with_max_level(tracing::Level::INFO)
    .init();
```

**Important:** Ensure tracing backends do not log sensitive material. Use `#[instrument(skip_all)]` on functions that handle secrets.

## Troubleshooting

### Authentication failures

**Symptom:** Clients cannot authenticate, `ihp.decrypt.failure` metrics high

**Checklist:**
1. Verify `K_master` matches across all service instances
2. Check `ServerEnvHash` matches expected value
3. Verify `allowed_versions` includes client's protocol version
4. Check `max_timestamp_drift` - may be too strict for clock skew
5. Review TLS exporter key derivation (if using TLS)
6. Check for nonce reuse (if tracking enabled)

**Resolution:**
- Rotate keys if mismatch detected
- Adjust `max_timestamp_drift` if legitimate clock skew
- Update `allowed_versions` if version mismatch

### Clock skew issues

**Symptom:** `ihp.drift.seconds` histogram shows high values, `ihp.decrypt.drift_rejected` spikes

**Diagnosis:**
- Check NTP synchronization on servers
- Review `max_timestamp_drift` configuration
- Compare server time with authoritative time source

**Resolution:**
- Fix NTP configuration
- Temporarily increase `max_timestamp_drift` if needed (within `MAX_ALLOWED_DRIFT_SECONDS`)
- Monitor drift histogram to confirm fix

### Version mismatch

**Symptom:** `ihp.decrypt.version_rejected` or `ihp.encrypt.version_rejected` spikes

**Diagnosis:**
- Check client protocol version vs server `allowed_versions`
- Review recent deployments for version changes

**Resolution:**
- Update `allowed_versions` in `IhpConfig` to include client version
- Coordinate client/server version upgrades
- Use version rollback procedure if needed

### Performance issues

**Symptom:** High latency, authentication timeouts

**Diagnosis:**
- Profile key derivation (HSM latency if using HSM-backed provider)
- Session key derivation overhead
- Network latency for RTT measurement

**Resolution:**
- Cache profile keys (if safe for your threat model)
- Optimize HSM access patterns
- Review RTT measurement frequency
- Consider async key derivation if blocking

### Nonce reuse detection

**Symptom:** `ihp.decrypt.failure` with `NonceReuse` error code

**Diagnosis:**
- Check if nonce tracking is enabled (if implemented)
- Review client nonce generation (should use CSPRNG)
- Verify nonce uniqueness per session

**Resolution:**
- Fix client nonce generation if deterministic
- Enable server-side nonce tracking if not already enabled
- Rotate keys if nonce reuse was exploited

## Incident response

- **Suspected key exposure:** rotate `K_master` in the HSM; redeploy services with the new key and invalidate existing sessions. Golden fixtures and KATs help confirm no accidental wire changes during rotation.
- **Version mismatch alerts:** adjust `allowed_versions` in `IhpConfig` and ship updated binaries. Reject unknown versions by default.
- **Replay/tamper detection:** investigate spikes in `ihp.decrypt.header_mismatch` or `ihp.decrypt.failure`; consider regenerating `ServerEnvHash` if hosts were re-imaged.

## Fuzzing and regression checks

- Run `cargo test` (with network access) to execute unit tests, KATs, and property tests.
- Use `cargo fuzz run capsule_roundtrip` / `nonce_mutation` (nightly + `cargo-fuzz`) to stress parsing and nonce handling.
- Keep the `golden_capsule_v1.json` fixture in sync with protocol changes; tests decrypt it with known keys.
