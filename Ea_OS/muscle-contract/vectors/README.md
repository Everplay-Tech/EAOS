# Muscle Contract Vectors

Use the generator to produce deterministic vectors for cross-implementation testing.

Command:

```
cargo run -p muscle-contract --bin muscle-contract-gen --features serde > \
  muscle-contract/vectors/v6_vector_01.json
```

Notes:
- The generator uses a deterministic nonce for repeatable output.
- Production builds MUST use random nonces.
