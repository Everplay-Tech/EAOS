# Compression Ratio Comparison Against Industry Baselines

## Overview

This study quantifies how the QYN-1 morpheme compression system performs against
established formats across 52 open-source projects that span Python, JavaScript,
Go, Rust, and C++. The comparison covers:

* Raw source archives
* gzip and brotli compressed source code
* JavaScript minification combined with gzip (where applicable)
* Mozilla's binary AST format approximations
* QYN-1 packages encoded with the new **balanced**, **maximum**, and
  **security** presets introduced in this revision

The underlying metrics originate from
[`data/compression_ratio_comparison.json`](../data/compression_ratio_comparison.json).
The helper script `scripts/benchmark_compression_ratio.py` loads the dataset and
emits derived ratios and summary statistics for downstream analysis.

## Methodology

1. Representative projects were grouped into eight cohorts (web, data science,
   frontend, Node services, and four flavours of systems programming).
2. For each project we measured the source archive size and recompressed the
   payload using gzip, brotli, and binary AST style encodings.
3. JavaScript workloads additionally capture minified and minified+gzip sizes to
   mirror industry deployment strategies.
4. The same ASTs were encoded with the three QYN-1 compression modes:
   * **Balanced** – per-file token optimisation and the default preset surfaced
     by the CLI.
   * **Maximum** – project-level optimisation with shared string tables and the
     new token remapping plan.
   * **Security** – disables shared state and emphasises deterministic but
     conservative compression.
5. Ratios were computed relative to the raw source archive and aggregated into
   mean/median/stdev statistics for quick comparison.

## Headline Results

* **Maximum** compression delivered a mean ratio of **0.387×** the original
  source size, comfortably ahead of gzip (0.511×) and brotli (0.451×), while
  beating the synthetic binary AST baseline (0.539×).
* The default **Balanced** preset averaged **0.429×**, providing deterministic
  outputs with minimal configuration.
* The **Security** preset remained competitive at **0.506×**, intentionally
  trading cross-file sharing for isolation while still matching gzip in most
  workloads.
* JavaScript projects benefited further from minification, but the **Maximum**
  mode still compressed to within ~10% of minified+gzip packages, while offering
  authenticated metadata and language-agnostic packaging.

## Observed Patterns

* String-heavy Python and JavaScript services consistently gained from the new
  frequency-driven token remapping, showing 8–12% improvements when switching
  from Balanced to Maximum.
* Systems code with macro-heavy Rust/C++ sources exhibited slightly higher
  variance; however, project-level string table sharing smoothed repeated header
  inclusions and template instantiations.
* The Security preset is the recommended fallback when regulatory policies
  prohibit cross-file dictionaries—the ratios closely track gzip while keeping
  the morpheme encoding deterministic.

## Using the Dataset

Run the helper script to inspect the per-project ratios:

```bash
python scripts/benchmark_compression_ratio.py > compression_report.json
```

The resulting JSON file includes ratios for every comparator and an aggregate
summary block. This can feed modelling workflows when tuning ANS probability
models or evaluating alternative morpheme dictionaries.
