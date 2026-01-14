# Frequently Asked Questions

**How do I rotate keys?**
Use `quenyan init --generate-keys --force` to create a new master key and
update CI secrets. Existing packages can be re-encoded using the
incremental encoder.

**Can I keep comments and formatting?**
Yes. See `docs/metadata_preservation_strategy.md` for the metadata
ledger that preserves docstrings and formatting preferences alongside
the canonical stream.

**What happens if a morpheme is missing?**
The encoder emits `meta:unknown` tokens and the linter warns about them
(`quenyan lint`). Update the dictionary by regenerating with
`scripts/generate_dictionary.py`.

**Is the pipeline deterministic across machines?**
Determinism is guaranteed when using the same dictionary version and
compression preset. Regression tests in `tests/test_roundtrip.py` cover
this property.
