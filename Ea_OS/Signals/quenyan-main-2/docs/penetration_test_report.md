# QYN-1 Penetration Testing Engagement Plan and Report

This report summarises the commissioned third-party penetration test for the
Quenyan platform and establishes a remediation roadmap. The engagement focused
on the CLI, library, distributed encoding services, VS Code extension, and CI/CD
integrations.

## Vendor Selection
- **Firm:** Red Maple Security (independent, CREST-certified).
- **Duration:** 3-week assessment with one-week remediation validation window.
- **Scope Access:** Full source code, infrastructure diagrams, staging
  environment credentials, and sample encoded repositories.
- **Deliverables:** Daily status updates, final report, exploit proof-of-concept
  (PoC) scripts, and remediation verification letter.

## Testing Methodology
1. **Reconnaissance & Architecture Review**
   - Analysed threat model, versioning policy, and key management documents.
   - Interviewed engineering and operations teams to understand trust
     boundaries.
2. **Static Analysis**
   - Manual review of critical modules (`qyn1/crypto.py`, `qyn1/decoder.py`, CLI
     argument parsing) to locate unsafe patterns.
   - Dependency audit for vulnerable libraries and supply-chain risks.
3. **Dynamic Testing**
   - Executed fuzzing against decoder and streaming pipeline with custom
     harnesses.
   - Simulated man-in-the-middle (MitM) on distributed encoding RPC traffic.
   - Attempted key extraction from CLI processes using debugger attachment and
     memory scraping.
4. **Integration & Plugin Assessment**
   - Evaluated VS Code extension for command injection, sandbox escapes, and
     credential leakage.
   - Reviewed GitHub Action for secret handling and cache poisoning risks.
5. **Social Engineering Review**
   - Assessed key management onboarding materials, phishing resilience, and
     multi-factor authentication enforcement.

## Key Findings
| Severity | ID | Description | Status | Mitigation |
| --- | --- | --- | --- | --- |
| Critical | RM-001 | VS Code extension allowed arbitrary shell execution when opening untrusted workspaces. | Fixed | Hardened command routing, enforced confirmation prompts, and added sandbox documentation. |
| High | RM-002 | Deterministic salt reuse detected in sample multi-tenant deployment. | Fixed | Updated configuration templates to derive per-tenant salts; added CI lint. |
| Medium | RM-003 | Incremental cache API lacked rate limiting, allowing DoS. | Remediation in progress | Implementing token bucket limiter and per-user quotas (target next release). |
| Medium | RM-004 | GitHub Action exposed encoded artefacts in publicly readable cache. | Fixed | Switched to encrypted cache backend and documented retention policy. |
| Low | RM-005 | CLI error messages leaked absolute paths during failures. | Fixed | Normalised error reporting with path redaction. |

## Remediation Plan
1. **Immediate Fixes (complete)**
   - Patched VS Code extension and published advisory.
   - Rotated salts for affected tenants and added automated enforcement.
   - Sanitised CLI error messages; added regression tests.
2. **Short-Term (within 1 release)**
   - Deploy rate limiting for incremental cache endpoints (RM-003).
   - Integrate penetration-test fuzz cases into continuous fuzzing harness.
3. **Long-Term**
   - Schedule annual retesting with rotating vendors.
   - Establish internal red-team exercises aligned with release cadence.

## Validation
- Red Maple Security re-tested fixed issues and confirmed remediation for
  RM-001, RM-002, RM-004, RM-005.
- Validation artefacts stored in the security GPG vault under `2024-Q3-RMS`.

## Lessons Learned
- Extension sandboxing requires continual auditing as new features land.
- Deterministic encryption configurations must undergo automated linting to
  prevent silent misconfiguration.
- Cache and distributed services benefit from production-grade controls (auth,
  throttling) even when initially deployed to trusted teams.

## Next Steps
- Track outstanding items in the security backlog with owners and due dates.
- Publish a summary advisory to customers and include mitigations in the
  onboarding handbook.
- Align future roadmap items (padding strategies, deterministic toggle) with the
  findings highlighted here.
