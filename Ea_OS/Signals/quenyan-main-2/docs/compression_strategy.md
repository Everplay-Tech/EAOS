# Compression Strategy Decision Matrix

To choose the production compression pipeline for QYN-1 morpheme streams we evaluated
three modelling strategies against the requirements for deterministic packaging,
reasonable encoding throughput, and compact payloads that play well with the
authenticated envelope.

| Strategy | Description | Determinism | Model Overhead | Encoding Speed | Compression Ratio | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Static | Pre-train a global symbol frequency model from a reference corpus and ship the table with the encoder | High | None at runtime | Fast (no histogram pass) | Good when corpus matches training distribution, poor on outliers | Requires periodic re-training as the morpheme dictionary evolves |
| Adaptive | Build symbol histogram for every input stream and serialise the resulting table alongside the compressed payload | High (model derived from canonical tokens) | Needs table payload per stream | Additional histogram pass | Best on atypical inputs | Table must be shipped and validated for every package |
| Hybrid | Start from the static base distribution and blend file-specific adjustments (e.g., delta frequencies or importance sampling) | High | Small delta per file | Slightly slower than static | Close to adaptive while preserving stability | More complex decoder (needs to merge baseline and delta tables) |

## Selected Approach

We selected the adaptive strategy with bounded precision tables for the core rANS
backend. The histogram pass is inexpensive (\~300 \u03bcs on the sample workloads) and
produces per-stream tables that remain deterministic because they are derived from the
canonicalised token list. The resulting model is serialised using 12-bit precision and
consumed by both the built-in rANS codec and optional backends.

To stabilise payload size we pair the adaptive histogram with a frequency-ordered string
table that deduplicates identifier and literal payloads. The table is encoded using
prefix compression and length-prefixed UTF-8 segments, which reduces payload bytes by
roughly 38% on the reference corpus.【F:scripts/benchmark_compression.py†L60-L87】【F:data/morpheme_frequency_profile.json†L1-L27】

## Multi-stage Optimisation Pipeline

The current release layers several orthogonal optimisations to maximise the value of
the adaptive entropy model:

* **Token remapping:** `qyn1.token_optimisation` builds a frequency-ranked palette per
  stream (Balanced mode) or per project (Maximum mode). The smaller alphabet improves
  ANS table density and unlocks a 6–12% size reduction on string-heavy inputs.
* **Project sharing:** `ProjectCompressionPlanner` precalculates shared string tables
  and optimisation plans so related files reuse identical identifiers and morpheme
  subsequences. This is surfaced via the `--compression-mode=maximum` preset.
* **Configurable presets:** `CompressionConfig` exposes `balanced`, `maximum`, and
  `security` modes so operators can prioritise either compression ratio or isolation.
  The CLI forwards the selected preset to `encode_package`, which threads the options
  through the pipeline and serialises the optimisation metadata alongside the model.

The combination of these stages is reflected in the cross-format ratios published in
[`docs/compression_ratio_comparison.md`](compression_ratio_comparison.md).

## Future Adjustments

* **Static bootstrap**: If a large, public corpus becomes available we can snapshot the
  averaged histogram as a starting point and store per-file deltas instead of full
  tables. The helper functions in `qyn1.compression` already accept externally supplied
  models, making this swap straightforward.
* **Adaptive precision**: Current tables fix the precision at 12 bits. Profiling data
  shows that moving to 11 bits only degrades compression by \<1% on average but saves
  lookup memory. Future builds could dynamically select precision based on entropy
  estimates from `profile_morphemes.py`.
* **Context modelling**: The frequency data exposes recurring 3-gram patterns such as
  `construct:function` \u2192 `structure:identifier` \u2192 `construct:block`. Capturing these in a
  context-mixing model would improve entropy coding but requires more invasive changes
  to the decoder.
* **Cross-file identifier context**: Extend `ProjectCompressionPlanner` to emit per-project
  identifier ranks and annotate whether a symbol is module-local or exported. Files would
  reuse the shared ranks when available and fall back to file-local ordering when not,
  tightening the palette for large repos without coupling unrelated modules. The emitted
  metadata remains deterministic and can be verified during decode.
* **String-table micro-models**: Gate an optional offline-trained character LM for string
  table suffix bytes. The encoder should benchmark the learned model against the current
  rANS path and only include the extra model blob if the projected bits saved exceed the
  added header bytes and CPU cost. The baseline remains the pure table+ANS flow for
  deterministic reproducibility and easy sandboxing.
* **Identifier-conditioned token priors**: Use the observed identifier distribution within a
  file to bias the token model—e.g., modules dominated by `*_test` names are more likely
  to contain assertions and fixtures. Exposing this signal to the histogram builder lets us
  bias the static portions of the ANS alphabet without altering the canonical token order,
  keeping encode/decode symmetric while squeezing a few extra percent out of skewed
  modules.
