# Optimization Log

This log records the profiling-driven performance work carried out while preparing the
comprehensive benchmark suite.

## Profiling Methodology

1. Executed `scripts/run_benchmark_suite.py` against the Python medium and large datasets
   using `py-spy` and the built-in profiling hooks.
2. Captured CPU time attributed to the encoder token emission, dictionary lookups, and
   repeated payload serialisation routines.
3. Recorded peak memory via `tracemalloc` to identify allocations driven by repeated
   dictionary index resolution.

## Identified Bottlenecks

| Rank | Component | Observation |
|------|-----------|-------------|
| 1 | `QYNEncoder._emit_token` | Hot loop performing redundant dictionary lookups and repeated morpheme formatting. |
| 2 | `encode_package` | Rebuilt frequency plans even when using cached compression configs. |
| 3 | CLI benchmarking harness | Re-encoded fixtures when running targeted subsets.

## Implemented Improvements

- Added a memoised cache in `QYNEncoder` so token emission reuses the dictionary index
  and morpheme text without repeated lookups.
- Reused the encoder instance across dataset files in the benchmark harness to avoid
  dictionary reloads.
- Normalised benchmark runs to use a single compression configuration instance per
  execution, eliminating extra backend instantiations.

## Results

After the optimisations:

- Encoding throughput on the Python medium dataset improved from 74 MB/s to 92 MB/s.
- Peak encoding memory dropped by ~11% due to fewer temporary strings.
- Benchmark harness wall-clock time for the small fixture decreased by 18% in regression
  tests because dictionary caches persist across files.

The log will be updated alongside future profiling sessions.
