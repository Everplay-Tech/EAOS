# ADR 0002: AEAD and Key Hierarchy Strategy

## Status

Accepted

## Context

The initial reference encoder used a single passphrase-derived key with
random salts and nonces that were generated ad-hoc for every archive.
This made deterministic builds difficult and provided no rotation
metadata. Operators also needed better tooling to handle key hierarchy
rollovers without weakening nonce reuse protections.

## Decision

We introduced a structured key hierarchy implemented in `mcs_reference`:

- Master keys are derived from passphrases using PBKDF2 with 200k rounds.
- Project-level keys are produced via HKDF using rotation metadata that
  embeds a base64 encoded project salt and generation counter.
- File-level keys are derived from the project key with per-file salts
  provided by the entropy strategy.
- The `EntropyStrategy` now accepts caller supplied salts and nonces but
  records each usage per key identifier. Reuse is rejected unless a
  `NonceManager` implementation vouches for uniqueness (for example a
  shared registry service).

Archives now embed rotation metadata and provenance details that are fed
into the AEAD associated data. Any tampering with provenance (e.g. the
`created` timestamp) breaks authentication during decryption.

## Consequences

- Deterministic build pipelines can inject salts and nonces taken from a
  reproducible manifest, while `EntropyStrategy` prevents accidental
  reuse.
- Key rolling is modelled explicitly through `rotation_state` files and
  a new `keys roll` CLI command that increments the generation and emits
  fresh project salts.
- Consumers must capture deterministic provenance (commit timestamps or
  manifests). The CLI defaults to `SOURCE_DATE_EPOCH`,
  `GIT_COMMIT_TIMESTAMP`, or the rotation timestamp to avoid calls to the
  system clock.

## Future Work

- Integrate remote nonce registries via gRPC to enable multi-node
  builders to coordinate deterministic nonces.
- Extend the metadata schema with additional provenance attestations
  (e.g. in-toto statements) once upstream specifications stabilise.
