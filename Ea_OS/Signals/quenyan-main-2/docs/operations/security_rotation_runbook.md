# Security Rotations & Upgrade Runbook

This playbook defines the operational cadence, audit checkpoints, and rollback/upgrade procedures for cryptographic key rotations and morpheme dictionary updates. It is written for SRE and Security Engineering teams maintaining Quenyan in production and assumes the `mcs-reference` and `quenyan` CLIs are available on the path.

## Rotation Cadence

| Asset | Cadence | Accountable Owner | Required Artifacts |
| --- | --- | --- | --- |
| Human-operated encryption keys | Every 90 days or immediately after suspected exposure | Security Engineering | `kms-status.json` from `mcs-reference keys --json`, rotation receipts stored as `rotation-report.json`, updated KMS metadata store (e.g., `${HOME}/.quenyan/aws-kms.json`). |
| Service principal / machine keys | Every 180 days with automation; stagger by environment to reduce blast radius | SRE | Same as above plus CI secret distribution proof (pipeline variable audit log). |
| Morpheme dictionaries | Quarterly GA releases with monthly preview branches; mandatory update when breaking morpheme semantics are introduced | Language Platform + SRE | Versioned dictionary manifests under `resources/morpheme_dictionary*/`, migration outputs from `quenyan migrate` (new package plus `.bak` backup). |

## Audit Checkpoints

- **Pre-rotation validation**: export current key metadata via `mcs-reference keys --provider <provider> --key-id <id> --json > kms-status.json` and confirm `rotation_due` aligns to policy. Capture the current incremental state (`.ci/quenyan-state.json`) so re-encodes can be replayed if needed.
- **Change authorization**: attach `kms-status.json`, the planned rotation window, and impacted project list (from `mcs-reference project dependency-graph --json`) to the change request.
- **Post-rotation evidence**: archive `rotation-report.json`, the CI run link that distributed new secrets, and a sample descriptor decoded after rotation.
- **Dictionary upgrades**: store both the new dictionary payload and the `.bak` files created by `quenyan migrate` to prove reversibility. Keep migration stdout/stderr alongside the change ticket for diff review.

## Runbook: Encryption Key Rotation

1. **Snapshot current state**
   ```sh
   mcs-reference keys --provider aws --key-id alias/quenyan --json \
     --metadata-path ${HOME}/.quenyan/aws-kms.json > kms-status.json
   ```
   Validate `rotation_due` and `audit_trail` entries before proceeding.
2. **Execute rotation**
   ```sh
   mcs-reference keys --provider aws --key-id alias/quenyan --rotate --json \
     --metadata-path ${HOME}/.quenyan/aws-kms.json > rotation-report.json
   ```
   Distribute the updated metadata store to build agents and secret managers.
3. **Propagate and verify**
   - Re-run a representative encode using the new key metadata:
     ```sh
     mcs-reference project batch-encode \
       --passphrase "$QYN1_PASSPHRASE" \
       --project-root repo/ \
       --output-dir repo/.artifacts \
       --key-provider aws \
       --key-id alias/quenyan
     ```
   - Decode one artifact to ensure the `key_management` block reflects the rotated key.
4. **Rollback strategy**
   - Restore the previous metadata file from `kms-status.json` if validation fails.
   - Revert CI/CD secret versions and re-run `batch-encode` to reissue artifacts with the prior key metadata.
   - Document the failure mode and schedule a new rotation window once the defect is fixed.

## Runbook: Morpheme Dictionary Upgrade & Package Migration

1. **Stage the dictionary**
   - Generate or import the updated dictionary into a new versioned directory under `resources/morpheme_dictionary*/`.
   - Run internal review on the diff to catch semantic shifts (e.g., changed morpheme bindings) before release.
2. **Migrate existing packages**
   ```sh
   quenyan migrate package.qyn1 \
     --key .quenyan/keys/master.key \
     --target-dictionary=v2 \
     --output package.v2.qyn1
   ```
   The CLI writes `package.qyn1.bak`; archive it as part of the change record.
3. **Rebuild dependent artifacts**
   ```sh
   mcs-reference project incremental-rebuild \
     --passphrase "$QYN1_PASSPHRASE" \
     --project-root repo/ \
     --output-dir repo/.artifacts \
     --state-file .ci/quenyan-state.json
   ```
   Use the rebuild to republish packages that depend on dictionary-sensitive morphemes.
4. **Verification gates**
   - Run `quenyan lint` or decode a sample to confirm the new dictionary version is embedded in descriptors.
   - Compare migration outputs against `.bak` files to ensure no unexpected structural drift.
5. **Rollback strategy**
   - Restore the previous dictionary directory and redeploy packages from their `.bak` backups: `mv package.qyn1.bak package.qyn1`.
   - Flush incremental state if necessary (`rm .ci/quenyan-state.json`) before re-running `incremental-rebuild` with the prior dictionary version.

## Monitoring & Alerting Expectations

- **Rotation horizon alerts**: schedule `mcs-reference keys --provider <provider> --key-id <id> --json > kms-status.json` nightly. Alert when `rotation_due` is within 14 days; page on-call if overdue.
- **Event stream checks**: forward `key-rotation` and `key-metadata` events to the SIEM; alert on failed rotations or mismatched `key_version` between environments.
- **Dictionary drift detection**: include dictionary version identifiers in deployment metadata and emit a control-plane alert when a package still references an out-of-policy version after migration.
- **Runbook compliance**: dashboards should track the age of the latest `rotation-report.json` and the presence of recent migration backups to prove rollback readiness.
