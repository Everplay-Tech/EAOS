# QYN-1 STRIDE Threat Model

This document applies STRIDE analysis to the Quenyan (QYN-1) encoding pipeline,
covering the CLI, library, distributed encoding services, metadata stores, and
resulting `.mcs` artefacts. Each threat includes an attack scenario, impact,
likelihood assessment, and mitigation roadmap.

## Spoofing
- **Scenario:** An attacker distributes a malicious binary or CLI wrapper that
  impersonates the official encoder, causing teams to encode source with an
  untrusted tool that leaks keys or plaintext.
- **Impact:** Catastrophic loss of confidentiality and integrity; stolen keys
  undermine every file encoded with the spoofed tool.
- **Likelihood:** Medium. Open-source distribution reduces barriers for
  attackers, but published checksums and package signatures raise the bar.
- **Mitigations:**
  - Sign official releases and publish reproducible build instructions.
  - Enforce checksum verification in CI templates and package manager
    integrations.
  - Document trusted distribution channels in onboarding materials.
  - Provide an `quenyan verify --check-signature` workflow tied to release
    metadata.

## Tampering
- **Scenario:** An adversary modifies `.mcs` files in transit or at rest,
  attempting to inject malicious payloads or alter metadata (e.g., source hash,
  morpheme dictionary version).
- **Impact:** High. Modified payloads could lead to corrupted decoding, while
  metadata tampering might disguise stale or malicious content.
- **Likelihood:** Medium. Standard transport protections mitigate most cases,
  yet insider threats remain plausible.
- **Mitigations:**
  - Continue using AEAD (ChaCha20-Poly1305) with authenticated metadata,
    including dictionary versions and source digests.
  - Reject packages failing tag verification and surface clear alerts in the
    CLI and APIs.
  - Maintain tamper-evident logs (append-only, signed) for repository archives
    and distributed encoding shards.
  - Encourage optional secondary signatures for high-assurance deployments.

## Repudiation
- **Scenario:** A contributor denies having encoded or migrated a package after
  distribution, complicating incident response.
- **Impact:** Medium. Attribution gaps hinder forensics and compliance audits.
- **Likelihood:** Medium-low. Encoding workflows are typically automated, but
  manual invocations occur.
- **Mitigations:**
  - Log encoder identity, timestamp, and tool version within authenticated
    metadata when a signing key is available.
  - Integrate with CI/CD attestation (e.g., Sigstore, in-toto) to bind builds to
    identities.
  - Preserve write-once audit trails in repository archives and incremental
    caches.

## Information Disclosure
- **Scenario:** Attackers inspect morpheme frequency histograms or metadata to
  infer code behaviour, or exploit misconfigured storage to access plaintext.
- **Impact:** High. Leaking structural information diminishes confidentiality.
- **Likelihood:** Medium. Deterministic encryption and structured tokens expose
  statistical signals.
- **Mitigations:**
  - Offer compression presets that add padding or noise to morpheme streams when
    stronger concealment is required.
  - Encrypt metadata caches and enforce strict access controls on key material.
  - Provide guidance for rotating deterministic keys and salts, limiting reuse.
  - See `docs/morpheme_information_leakage.md` for quantitative leakage
    analysis and mitigation roadmap.

## Denial of Service
- **Scenario:** Crafted inputs (deeply nested ASTs, billion-character tokens,
  malformed morpheme sequences) exhaust encoder/decoder resources or trigger
  worst-case behaviours.
- **Impact:** Medium-high. Build pipelines can be halted, impacting release
  velocity.
- **Likelihood:** Medium. Attack requires repository commit access or malicious
  supply-chain package.
- **Mitigations:**
  - Keep the existing streaming parser, chunked encoding, and memory ceilings
    enabled by default.
  - Enforce timeouts and resource quotas in distributed workers.
  - Expand fuzzing and property-based testing coverage (see
    `docs/edge_case_testing.md`).
  - Add rate limiting and authentication to remote encoding services.

## Elevation of Privilege
- **Scenario:** Exploiting decoder bugs or unsafe integrations to execute code
  with elevated permissions during decode (e.g., via plugin hooks or unsafe
  deserialisation).
- **Impact:** Critical. Compromise could yield project keys or broader system
  access.
- **Likelihood:** Low-medium. The Python implementation is sandboxed, yet
  third-party integrations (VS Code extension, CI plugins) expand the surface.
- **Mitigations:**
  - Adopt defence-in-depth: run decoding in constrained containers or
    sandboxes for CI and IDE tooling.
  - Conduct regular security code reviews and professional penetration testing
    (see `docs/penetration_test_report.md`).
  - Minimise dynamic code execution in plugins; prefer declarative formats.
  - Enable optional hardware-backed key isolation where available.

## Mitigation Roadmap
1. Formalise release signing and attestation within the next release cycle.
2. Ship configurable padding/noise strategies for high-confidentiality use
   cases.
3. Expand fuzzing harnesses and integrate coverage-guided fuzzers in CI.
4. Engage third-party penetration testers annually and track remediation in the
   security backlog.
5. Harden remote services with authentication, quota enforcement, and runtime
   isolation policies.
