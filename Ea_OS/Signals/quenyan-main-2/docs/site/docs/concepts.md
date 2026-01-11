# Conceptual Guide

Quenyan bridges static analysis, linguistics, and cryptography. This
section introduces the core ideas at multiple levels of expertise.

## Abstract Syntax Trees

- **Beginners**: Quenyan normalises Python ASTs into a deterministic form
  using the universal schema from `docs/universal_ast.schema.json`.
- **Practitioners**: Nodes map to Quenya morphemes recorded in
  `resources/morpheme_dictionary_v1/dictionary.json`.
  `qyn1/resources/morpheme_dictionary/v1_0/dictionary.json`.
- **Experts**: Node ordering, optional field canonicalisation, and
  language adapters are described in `docs/universal_ast_mapping.md`.

## Morphemes & Encoding

Morpheme entries capture linguistic justification, AST mappings, token
frequency, and binary encodings. Read the detailed dictionary in
`docs/quenya_morpheme_dictionary_v1.md` for the full inventory.

## Compression & ANS

`docs/compression_strategy.md` and
`docs/compression_ratio_comparison.md` explain how variable-length token
plans, ANS backends, and string tables compose the multi-stage pipeline.

## Cryptography

The architecture and nonce strategy live in
`docs/cryptographic_architecture.md` and `docs/encryption_mode_spec.md`.
Authenticated metadata ensures tampering is detected during decode or
verification.
