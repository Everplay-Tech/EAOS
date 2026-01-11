# MCS Standardisation Plan

This document tracks the activities required to submit the MCS specification to
formal standards bodies and to coordinate multi-vendor adoption.

## Target Venues

| Organisation | Artefact            | Status        | Notes |
|--------------|---------------------|---------------|-------|
| IETF         | Internet-Draft (MCS)| Drafting      | Target Security Area, COSE integration |
| Ecma         | Technical Report    | Exploring     | Align with language tooling ecosystem |
| ISO/IEC JTC 1| NP Submission       | Researching   | Requires national body sponsorship |

## Deliverables

1. **Internet-Draft skeleton** – based on `docs/mcs_format_v1_specification.md`,
   with normative language converted to RFC 2119 terms. Draft tracked under
   `reference/standards/ietf-draft-mcs.md`.
2. **Reference implementations** – maintained in `reference/python`,
   `reference/js`, `reference/rust`, and `reference/go` with identical conformance
   tests (see `tests/test_reference_impls.py`).
3. **Test vectors** – updated quarterly from the compatibility archive and
   published alongside the draft for implementers.

## Timeline

| Phase | Duration | Exit Criteria |
|-------|----------|---------------|
| Preparation | Q1 | Complete draft, collect feedback from early adopters |
| Working Group Adoption | Q2 | Present at IETF CFRG/SECDISPATCH, secure adoption |
| Iteration | Q3 | Address review comments, run interop events |
| Publication | Q4 | Submit final draft, begin Ecma/ISO engagement |

## Stakeholders

* **Quenyan Core** – primary editors and maintainers.
* **Tooling Vendors** – IDE and CI/CD integrators participating in interop
  workshops.
* **Academic Partners** – contribute formal analysis of compression and security
  properties.

## Tracking

Progress is tracked via GitHub milestones `standardisation-phase-*`. Meeting
notes and consensus calls are recorded in `docs/standardisation/minutes/`.

