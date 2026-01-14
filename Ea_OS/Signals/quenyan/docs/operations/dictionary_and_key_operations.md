# Dictionary & Key Operations Guide

This guide defines the operational lifecycle for morpheme dictionaries and encryption keys, including rotation schedules, rollout/rollback steps, audit and readiness checks, and incident response expectations. It is designed for SRE, Security Engineering, and release owners who operate Quenyan in regulated environments.

## Ownership & RACI

| Activity | Accountable (A) | Responsible (R) | Consulted (C) | Informed (I) |
| --- | --- | --- | --- | --- |
| Dictionary GA/preview releases | Language Platform Lead | SRE Release Engineer | Security Engineering, QA | Product, Dev Leads |
| Key rotations (human + service principals) | Security Engineering Manager | SRE On-Call | Compliance | Dev Leads |
| Rollbacks (dictionary or key metadata) | SRE Incident Commander | SRE On-Call | Security Engineering | Stakeholders in affected environment |
| Package migrations to new dictionary versions | SRE Release Engineer | Build/CI Owner | Language Platform | Dev Leads |

## Rotation Schedules

- **Morpheme dictionaries**
  - **Preview**: Monthly preview drops for early adopters; publish diffs and semantic changes.
  - **GA**: Quarterly general-availability cadence; enforce upgrades within 30 days of GA.
  - **Hotfix**: Out-of-band releases only for security or semantic correctness regressions; must include a rollback-ready `.bak` set for all affected packages.
- **Encryption keys**
  - **Human-operated**: Rotate every 90 days or immediately after suspected exposure. Maintain `rotation-report.json` per event.
  - **Service principals/machines**: Rotate every 180 days; stagger by environment to minimize blast radius. Capture CI distribution logs for audit.

## Runbook: Dictionary Rotation & Package Upgrade

1. **Pre-flight audit (T-7 to T-3 days)**
   - Export current dictionary usage: `mcs-reference project dependency-graph --json > dictionary-usage.json`.
   - Capture current state for reproducibility: `cp .ci/quenyan-state.json .ci/quenyan-state.pre-rotation.json` (if present).
   - Validate preview builds against the new dictionary using staging keys; record outcomes in the change ticket.
2. **Stage the new dictionary**
   - Place the new version under `resources/morpheme_dictionary*/` with a unique versioned directory (e.g., `v2/`).
   - Run semantic drift review: diff morpheme bindings and update the release notes in `resources/morpheme_dictionary*/CHANGELOG.md`.
3. **Migrate packages**
   - Execute migration per package:
     ```sh
     quenyan migrate <package>.qyn1 \
       --key .quenyan/keys/master.key \
       --target-dictionary=<target_version> \
       --output <package>.<target_version>.qyn1
     ```
   - Preserve automatically created backups (`<package>.qyn1.bak`) for rollback.
4. **Rollout & verification**
   - Run `mcs-reference project incremental-rebuild --state-file .ci/quenyan-state.json` to republish dependent artifacts.
   - Decode a sample package to confirm the embedded `dictionary_version` matches the target.
   - Push artifacts to staging, then production after sign-off from Security Engineering.
5. **Rollback steps**
   - Restore prior dictionary directory and revert packages using `.bak` files: `mv <package>.qyn1.bak <package>.qyn1`.
   - Revert `.ci/quenyan-state.json` to the pre-rotation copy and rerun `incremental-rebuild` with the prior dictionary version.
   - Document the failure mode and schedule a new rotation window once fixed.

## Runbook: Encryption Key Rotation

1. **Pre-flight checks**
   - Export key metadata: `mcs-reference keys --provider <provider> --key-id <id> --json > kms-status.json`.
   - Verify `rotation_due` and ensure downstream agents have permission to fetch updated metadata.
   - Confirm backup of current metadata store (e.g., `${HOME}/.quenyan/aws-kms.json`).
2. **Rotate**
   - Perform the rotation: `mcs-reference keys --provider <provider> --key-id <id> --rotate --json > rotation-report.json`.
   - Distribute updated metadata to CI/CD secret stores and agents.
3. **Propagate & validate**
   - Re-encode a representative project using the new metadata; decode one artifact to ensure the `key_version` reflects the rotation.
   - Store `rotation-report.json` and CI logs in the change request.
4. **Rollback steps**
   - Restore the previous metadata from `kms-status.json` or the archived metadata store.
   - Re-encode affected artifacts with the restored key metadata and republish them.
   - Notify stakeholders and create a corrective action plan before rescheduling rotation.

## SRE Readiness & Health Checks

- **Readiness gates (pre-change)**
  - ✅ `dictionary-usage.json` generated and reviewed; no orphaned packages targeting deprecated versions.
  - ✅ Backups of `.ci/quenyan-state.json`, dictionary directories, and key metadata captured.
  - ✅ Valid staging run with new dictionary/key metadata; decode checks match expected versions.
  - ✅ Pager duty / on-call rotation acknowledges the change window.
- **Automated checks (continuous)**
  - Nightly `mcs-reference keys --json` to flag `rotation_due` within 14 days; page if overdue.
  - Daily dictionary drift detector comparing deployed packages against the policy-compliant version; alert on mismatches.
  - CI/CD pre-flight to block deployments when package `dictionary_version` is behind GA by >30 days or key metadata is stale.
- **Audit intervals**
  - Weekly audit of `rotation-report.json` and `kms-status.json` age; confirm evidence is archived for the last two rotations.
  - Monthly review of dictionary preview adoption and semantic diff outcomes; ensure rollback artifacts remain intact.
  - Quarterly disaster-recovery rehearsal combining dictionary and key rollback to validate reversibility.

## Security Incident Runbooks (Dictionary/Key)

- **Dictionary tampering or semantic regression**
  1. **Detect**: Alerts from drift detector or failed decode checks; confirm via checksum of dictionary directory and decode sample.
  2. **Contain**: Freeze deployments; quarantine the affected dictionary version; switch pipelines to the last known-good directory.
  3. **Eradicate**: Replace compromised files from signed backups; regenerate hashes and publish a hotfix dictionary release.
  4. **Recover**: Redeploy packages from `.bak` backups; rerun `incremental-rebuild` with validated dictionary; close with postmortem.
- **Key compromise or rotation failure**
  1. **Detect**: SIEM alert on unauthorized key access, failed `key_version` propagation, or mismatch between environments.
  2. **Contain**: Disable affected principals in KMS; rotate credentials for build agents; halt package publication.
  3. **Eradicate**: Perform emergency key rotation with new key IDs; re-encrypt stored artifacts; invalidate old secrets in CI/CD.
  4. **Recover**: Run validation decode to confirm new `key_version` and dictionary continuity; update runbooks and audit evidence.

## Reporting & Metrics

- **Core KPIs**: percentage of packages on latest GA dictionary, mean time to rotate keys (MTTRot), mean time to recover from rotation failure (MTRR), and number of drift alerts acknowledged within SLA.
- **Evidence**: Store `rotation-report.json`, `kms-status.json`, dictionary diff reports, and `.bak` backup manifests alongside change tickets.
- **Escalation**: All critical findings route to the SRE Incident Commander with Security Engineering as co-owner; status updates every 30 minutes during incidents.
