# Disaster Recovery Runbooks

This guide describes the steps operators should follow when package artifacts, KMS metadata, or build infrastructure become unavailable.  The emphasis is on rapid detection (via the new structured logs) and safe recovery of encrypted data.

## 1. Incident Response Principles

- **Protect passphrases** – never embed the passphrase in tickets or chat rooms.  Use secret managers.
- **Preserve evidence** – retain CLI log streams (`project-incremental-file`, `key-rotation`) to build a clear timeline.
- **Restore deterministically** – rely on the descriptor JSON files stored in version control.  The CLI can always re-encode from source.

## 2. Loss of Artifact Storage

1. Regenerate artifacts from source:
   ```sh
   mcs-reference project batch-encode \
     --passphrase "$QYN1_PASSPHRASE" \
     --project-root repo/ \
     --output-dir restore-artifacts
   ```
2. Validate a sample package by decoding it and checking metadata integrity.
3. Upload regenerated artifacts to the new storage backend.
4. Emit a `dependency-graph --json` report to capture the exact package topology at the time of restoration.

## 3. Corrupted Incremental State File

1. Delete or quarantine the corrupted file (e.g., `.ci/quenyan-state.json`).
2. Run `incremental-rebuild` with an empty state file; the CLI will rebuild all descriptors and emit `rebuilt` events for each file.
3. Inspect the logs to ensure no files were skipped.
4. Archive the new state file and store it with restricted permissions.

## 4. Key Compromise or Forced Rotation

1. Use the `keys` command to rotate the affected key:
   ```sh
   mcs-reference keys --provider aws --key-id alias/quenyan --rotate --json > rotation-report.json
   ```
2. Distribute the new `rotation-report.json` to stakeholders.  The file includes the new version, next rotation window, and audit metadata.
3. Re-encode any outstanding packages to embed the updated key metadata into descriptor payloads.
4. Update monitoring alerts to track the new `rotation_due` date.

## 5. Build Infrastructure Outage

1. Detect the failure through missing `project-batch-encode` events in the log stream.
2. Fail over to a warm standby CI pipeline.  The reference workflows under `ci/pipelines/` can be used as templates.
3. Run `dependency-graph --json` once the new pipeline is operational to confirm the integrations detected by the CLI match expectations.

## 6. Tabletop Exercise Template

| Step | Objective | Artifact |
| --- | --- | --- |
| Prepare | Export key metadata (`mcs-reference keys --json`). | `kms-status.json` |
| Simulate | Delete artifact directory and rerun `batch-encode`. | `restore-artifacts/` |
| Validate | Decode packages, verify metadata section. | `decoded/*.json` |
| Review | Document lessons learned and update runbooks. | Incident report |

Routine practice of these exercises ensures teams can recover quickly without sacrificing the cryptographic guarantees of the Quenyan format.
