# MCS Standardisation Plan

This document tracks the work required to publish the Morphemic Container Stream
(MCS) format through an open standards body.  It accompanies the v1.0
specification and is updated as milestones are reached.

## 1. Candidate venues

| Venue | Rationale | Status |
|-------|-----------|--------|
| IETF (Internet Engineering Task Force) | Well established process for Internet-facing data formats; ability to publish an RFC that guides multi-vendor adoption. | Preferred |
| Ecma International | Relevant for developer tooling and scripting ecosystems, particularly JavaScript. | Investigating |
| ISO/IEC JTC 1/SC 22 | Long-term archival standard with focus on programming languages. | Deferred (higher cost) |

## 2. Internet-Draft roadmap (IETF)

1. **Problem statement** – articulate the need for a deterministic, encrypted AST
   transport format.  (Owner: @quenyan-spec; Due: 2024-07-15)
2. **Initial draft** – convert the v1.0 specification into XML2RFC format using
   `mcs-format-00`.  (Due: 2024-08-01)
3. **Working group selection** – present at the ARTAREA DISPATCH meeting to
   determine home WG (likely ART or SEC).  (Due: 2024-08-15)
4. **Draft revisions** – incorporate early feedback, especially around security
   considerations and deterministic encryption.  (Rolling milestone)
5. **Working group adoption** – seek adoption call once at least two
   implementations demonstrate interoperability (see §4).  (Due: 2024-09-30)
6. **Last Call & IESG review** – target 2024-12-01 for IETF Last Call submission.
7. **RFC publication** – estimated Q1 2025 following editorial revisions.

## 3. Stakeholder engagement

* **Cryptography reviewers** – liaise with CFRG volunteers to validate the
  deterministic AEAD envelope.
* **Language tooling vendors** – gather feedback from VS Code, JetBrains, and Go
  team representatives to confirm the format meets IDE integration needs.
* **Cloud providers** – coordinate with AWS KMS and Google Cloud KMS teams to
  ensure key-management guidance aligns with their offerings.

## 4. Reference implementations

The draft submission references three independent implementations (Python, Rust,
JavaScript).  Test vectors and conformance reports are published in
`reference/test_vectors/`.  Interop reports are attached to each Internet-Draft
revision to satisfy IETF requirements for at least two interoperable
implementations before advancement to Proposed Standard.

## 5. Change control

A standing **Format Design Team** meets bi-weekly to review errata and extension
proposals.  Membership currently includes Quenyan maintainers and volunteer
implementers from the partner ecosystems listed above.  All decisions are
published in the `docs/meeting-notes` directory.

## 6. Publication tracker

| Milestone | Target Date | Owner | Status |
|-----------|-------------|-------|--------|
| Draft skeleton prepared | 2024-07-15 | @quenyan-spec | In progress |
| XML2RFC tooling pipeline | 2024-07-30 | @quenyan-build | Blocked on tooling PR |
| WG adoption call | 2024-09-30 | @quenyan-spec | Pending |
| Interop bake-off | 2024-10-15 | @reference-lead | Scheduled |
| IETF Last Call | 2024-12-01 | @quenyan-spec | Pending |

## 7. Deliverables

* XML2RFC source (`draft-quenyan-mcs-00.xml`).
* Companion GitHub repository with issues enabled for feedback.
* Mailing list updates following each revision.
* Public conformance test harness.

## 8. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Cryptographic concerns over deterministic AEAD | Engage CFRG early, provide formal proofs and optional randomised mode |
| Reference implementations diverge | Maintain shared test vectors and CI cross-checks |
| Resource constraints for standardisation | Partner with academic collaborators to co-author the draft |

## 9. Next steps

* Finalise XML2RFC skeleton and publish pre-draft for community review.
* Schedule presentation slot at the next IETF meeting.
* Continue growing the registry of real-world adopters to demonstrate demand.
