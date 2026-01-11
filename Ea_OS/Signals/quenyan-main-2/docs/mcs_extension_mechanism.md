# MCS Extension Mechanism

This note expands §17 of the MCS v1.0 specification and provides normative
examples for extending the container format without breaking backward
compatibility.

## Goals

* Permit vendors to ship experimental data while maintaining interoperability.
* Enable future standardisation work to formalise successful extensions.
* Preserve deterministic serialisation guarantees for canonical packages.

## Extension Slots

* **Section identifiers**: `0x7F00`–`0x7FFF` are reserved for optional sections.
  * `0x7F00` – Generic key/value manifest (JSON payload).
  * `0x7F01` – Detached signature block (COSE_Sign1 payload).
  * `0x7F02` – Dictionary delta (binary patch against canonical dictionary).
* **Flag bits**: unused bits in existing section headers are reserved and MUST be
  zero. Writers MAY repurpose a reserved bit only after negotiating the feature
  via metadata capabilities.
* **Reserved bytes**: padding and zero-length sentinels in the STREAM section are
  intended for future hash identifiers, encoding hints, or compression toggles.

## Negotiation Workflow

1. Writers set `metadata.capabilities` to a sorted list of feature identifiers
   (e.g., `"extension.signature.cose"`).
2. Readers scan the list and determine if all required capabilities are
   supported. Unsupported hard requirements MUST abort decoding.
3. Optional capabilities (prefixed `"+"`) MAY be ignored by the reader while
   retaining payload bytes for authentication.

## Example: Embedding a COSE Signature

1. Writer computes a detached COSE_Sign1 signature over the concatenation of the
   wrapper header and payload bytes.
2. The signature is placed in a new section with ID `0x7F01`, zero flags, and a
   length-prefixed payload.
3. `metadata.capabilities` includes `"extension.signature.cose"`.
4. Readers that support the feature verify the signature prior to releasing the
   decoded descriptor. Readers that do not support the feature still authenticate
   the AEAD envelope and may ignore the extension section after integrity checks.

## Example: Shipping a Dictionary Delta

1. Writer computes a binary patch (bsdiff) between the baseline dictionary and a
   project-specific variant.
2. The patch is emitted as section `0x7F02` with a descriptor JSON payload that
   names the base dictionary version and hash.
3. `metadata.capabilities` includes `"extension.dictionary.delta"`.
4. Readers apply the delta after validating the base dictionary hash.

## Extension Registration

Vendors are encouraged to register extension identifiers in `docs/extension_registry.md`
with the following fields:

| Field          | Description                                              |
|----------------|----------------------------------------------------------|
| Identifier     | Stable snake_case string (e.g., `extension.foo.bar`).    |
| Section ID     | Hexadecimal identifier or `n/a` if capability-only.      |
| Owner          | Organisation or project maintaining the extension.       |
| Contact        | Support or mailing list address.                         |
| Specification  | Link to public description and conformance requirements. |

The registry is version-controlled to ensure long-term discovery and to prevent
collisions.

## Determinism Considerations

* Extension payloads MUST be canonical with respect to their own data model.
* Writers MUST NOT emit duplicate extension sections with the same identifier.
* Capability lists are sorted lexicographically to guarantee reproducible output.

## Future Work

* Define a compact binary schema for frequently used extension payloads.
* Explore streaming negotiation so that partial decoding is possible when only a
  subset of extensions are required.
* Align extension naming with the proposed standardisation drafts (see
  `docs/standardisation_plan.md`).

