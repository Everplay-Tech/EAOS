# Internet-Draft Skeleton: Morpheme Container Stream (MCS)

This draft skeleton captures the structure for an eventual IETF submission.

## Abstract

The Morpheme Container Stream (MCS) format defines a deterministic, encrypted
representation of language-agnostic abstract syntax trees. It integrates
compression, authenticated metadata, and extension negotiation for secure source
code interchange.

## Requirements Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" are to be
interpreted as described in RFC 2119 and RFC 8174.

## Document Structure

1. Introduction
2. Terminology
3. Format Overview (mirrors `docs/mcs_format_v1_specification.md`)
4. Cryptographic Considerations
5. IANA Considerations (section/extension registry)
6. Security Considerations
7. Implementation Status (references multi-language implementations)

## Open Items

* Decide working group (COSE vs. SEC AREA dispatch).
* Determine whether to register media type `application/mcs+binary`.
* Align extension registry with IANA processes.

