## Reporting a Vulnerability

- Email security reports to **security@quenyan.example.com** with a clear subject line, affected components, reproduction steps, impact statement, and any temporary mitigations.
- Do **not** open public issues or pull requests for suspected vulnerabilities.
- For encrypted communication, use the PGP key (fingerprint: `F4A1 7C82 D2B7 9D44 59A1  1E0F 7AF9 2F0A 3E86 7D11`) published at `https://security.quenyan.example.com/pgp.txt`. Include your preferred public key for coordinated disclosure.

## Responsible Disclosure & Service Levels

- **Acknowledgement:** Within **2 business days** of receipt.
- **Initial triage & reproduction:** Within **5 business days**; reporter will be asked for clarifications if required.
- **Remediation plan:** Delivered within **10 business days** of successful reproduction, including target release date and mitigations.
- **Fix and coordinated disclosure:** High/critical issues targeted for resolution within **30 days**; medium/low within **90 days**, or on a mutually agreed timeline. Public disclosure occurs only after a fix or mitigation is available unless the reporter prefers a different timeline.
- **Secure collaboration:** Updates are shared over the original encrypted thread when PGP is used; otherwise via the security alias with optional signed messages.

## Security Contacts & Escalation

- Primary: **security@quenyan.example.com**
- Secondary (operational escalation): **oncall-security@quenyan.example.com**
- Include a secure callback channel for high-sensitivity details; the on-call team can initiate mutually agreed encrypted channels for log and exploit artifact transfer.

## Triage & Handling Flow

1. **Intake:** Reports are logged in the private security queue with severity classification (CVSS-inspired), affected assets, and ownership mapping.
2. **Reproduction:** Security engineers validate issues in isolated environments. Incomplete reports trigger requests for missing details; reporter-provided proof-of-concept code is stored in restricted locations.
3. **Containment:** If exploitation is possible, temporary mitigations (feature flags, firewall rules, credential rotation, or access revocation) are deployed immediately.
4. **Remediation:** Owning teams deliver fixes; security reviews the patch, automated tests, and change-management sign-off before release.
5. **Validation:** Post-fix verification includes regression tests, negative test cases mirroring the exploit path, and dependency scanner reruns when applicable.
6. **Communication:** Reporters are updated at each milestone; coordinated disclosure timing is revisited after validation.

## Cryptographic Key Management

- **Storage:** Keys, certificates, tokens, and signing materials reside only in approved secret managers (cloud KMS/SM) with audit logging; never commit keys to source control or build logs.
- **Access:** Enforce least privilege, MFA, short-lived credentials, and hardware-backed signing for release artifacts where available.
- **Rotation:** Human-accessed keys rotate at least every **90 days**; service principals every **180 days** or on supplier guidance; immediate rotation after suspected exposure.
- **Lifecycle:** Track provenance, expiry, and revocation; retire old keys from allowlists and distribution lists after rotation. Use dual control for sensitive revocations.

## Dictionary Upgrades & Rollbacks

- Security-sensitive dictionaries (stopword/deny/normalization lists) must be versioned and changelogged.
- **Upgrade process:** Review for backward compatibility and bypass vectors; stage in lower environments with telemetry for false positives/negatives; require peer security review before promotion.
- **Rollback process:** Maintain the previous dictionary version in artifact storage; rollback requires validation of restored behavior and reinstating monitors to confirm stability.
- **Change control:** All upgrades/rollbacks are tracked via change tickets with owner, approver, and deployment window.

## Incident Response & Timelines

1. **Detect & declare:** Confirm the incident, assign an incident commander, and create a private channel within **30 minutes** of declaration.
2. **Assess & contain:** Scope affected systems, isolate compromised credentials, enable verbose audit logging, and apply temporary controls; aim to complete initial containment within **4 hours** for high/critical events.
3. **Eradicate & recover:** Patch or revert offending changes, rotate keys/secrets, restore from trusted backups, and validate system integrity; target restoration of critical services within **24 hours** where feasible.
4. **Communicate:** Notify stakeholders (leadership, affected customers as required) with periodic updates and an ETA for remediation; provide the reporter with progress aligned to the disclosure SLA.
5. **Post-incident:** Complete a blameless postmortem within **5 business days**, documenting the timeline, root cause, lessons learned, and corrective actions tracked to closure.

## Dependency Scanner Integration & Ownership

- **Dependabot:** Enabled for all supported ecosystems with a **weekly** update cadence; security patches generate pull requests automatically. Owning service teams triage Dependabot alerts within **48 hours** for high/critical severities and within **5 business days** for medium/low.
- **Snyk (or equivalent):** Continuous monitoring on default and release branches with PR gating for SAST/OSS findings. Security and the owning team jointly review blockers; high/critical issues without fixes require documented compensating controls and target remediation plans.
- **Triage ownership:** Security engineering runs a weekly review to deduplicate findings across tools, open remediation tickets, and track SLAs. Exceptions require time-bound risk acceptance approved by security leadership.

## Operational Runbooks

- Refer to the [Security Rotations & Upgrade Runbook](../docs/operations/security_rotation_runbook.md) for key rotation cadence, morpheme dictionary upgrade procedures, audit checkpoints, and rollback guidance.

## Data Handling & Logging for Security Events

- Logs related to security events must be retained per policy, protected from tampering, and scrubbed of secrets.
- Access to security-event telemetry is restricted to least-privilege security and SRE roles; sharing externally requires approval.
