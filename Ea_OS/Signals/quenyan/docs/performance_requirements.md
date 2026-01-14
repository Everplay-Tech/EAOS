# Performance Requirements and Baseline Measurements

This document defines throughput and size targets for the QYN-1 morpheme
pipeline and captures the empirical baseline produced by the reference
implementation.

## Target Thresholds

| Area | Requirement |
| ---- | ----------- |
| Encoding throughput | ≥ **0.50 MB/s** for project batches using the parallel encoder with streaming enabled |
| Decoding throughput | ≥ **1.00 MB/s** for package materialisation (decode → AST → canonical source) |
| Compression overhead | Morpheme encoding + ANS compression should be **≤ 35% slower** than `gzip -6` on the same input |
| Size delta | Final encrypted packages should expand source archives by **≤ 25%** before ANS post-processing |

The throughput targets assume multi-file batches where the pipeline can
exploit file-level parallelism. Single-file workloads are expected to land
within 15% of the headline numbers thanks to streaming chunking.

## Baseline Measurements

The `scripts/benchmark_performance.py` utility runs the reference pipeline
against synthetic projects to capture comparative timings. The latest run
produced the following baseline summary:

| Metric | Result |
| ------ | ------ |
| Python AST parsing | **0.27 MB/s** |
| Gzip compress / decompress | **141 MB/s / 844 MB/s** |
| ChaCha20-Poly1305 encrypt / decrypt | **0.17 MB/s / 0.16 MB/s** |
| Streaming morpheme encode throughput | **0.017 MB/s** across 4 files |

Full measurement output is tracked in `data/performance_baseline.json` for
repeatability.【F:data/performance_baseline.json†L1-L14】 The encoder currently
falls short of the target throughput by ~19×, so optimisation work should focus
on parallel fan-out and reduced per-symbol overhead.

## Gap Analysis

* **Encoding bottleneck:** The baseline throughput is dominated by the pure
  Python morpheme encoder and the chunked ANS backend. Meeting the 0.50 MB/s
  target requires an ~19× improvement, motivating the parallel execution plan
  outlined in the profiling report.
* **Compression overhead:** Gzip remains two orders of magnitude faster than the
  reference ANS implementation. The 35% overhead target can be met once the
  chunked backend is ported to a vectorised extension or backed by a native
  rANS kernel in production builds.
* **Package size:** The benchmark workload produced an encrypted payload that is
  1.9× larger than the raw source because of per-chunk metadata. Tuning chunk
  sizes and sharing frequency tables will be required to stay within the 25%
  expansion ceiling while holding peak RSS to the observed ~35 MB.

These targets feed directly into the optimisation plan documented in
`docs/performance_profiling.md`.
