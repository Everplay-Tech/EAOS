# Quenyan Benchmark Suite

The benchmark suite provides reproducible measurements across representative open-source
projects. Datasets are grouped by size and cover Python, JavaScript, Go, Rust, and Java
codebases spanning web, systems, data, mobile, and developer tooling workloads.

## Dataset Manifest

Datasets are defined in [`data/benchmark_suite_manifest.json`](../data/benchmark_suite_manifest.json).
Each entry records:

- `slug`: stable identifier used by tooling.
- `category`: size bucket (`small`, `medium`, `large`, `huge`).
- `language` and `domain`: to ensure language and workload diversity.
- `download` metadata: canonical URL, optional checksum, and optional archive subdirectory.
- `entry_glob`: glob patterns selecting source files.
- `local_fixture`: optional path for lightweight regression fixtures.

Manifest entries reference immutable release artifacts (Git tags, tarballs, or
commit snapshots) so the suite can be executed offline once downloaded. Each dataset
maps to a public repository with liberal licensing suitable for benchmarking.

## Running the Suite

Use the helper script to execute benchmarks:

```bash
python -m scripts.run_benchmark_suite \
  .benchmarks/workspace \
  .benchmarks/output \
  --results suite_results.json \
  --languages python javascript \
  --categories small medium
```

The script will:

1. Load the manifest and filter datasets by slug, language, or size category.
2. Download and extract archives into the workspace directory when needed.
3. Encode each project using the configured morpheme pipeline and collect metrics:
   - Encoding / decoding wall-clock time
   - Peak memory (via `tracemalloc`) for encode/decode
   - Compression ratio vs. original and gzipped source
   - Aggregate MCS overhead (difference between encoded size and compressed tokens)
4. Emit a JSON summary compatible with downstream dashboards.

Datasets in languages that are not yet supported by the current encoder are recorded as
"skipped" in the output unless `--strict` is provided. The `tests/data/benchmarks`
fixture ensures the harness is exercised without requiring large downloads.

## Output Format

`scripts/run_benchmark_suite.py` produces a JSON file containing:

- `manifest_version`: manifest schema version
- `results`: array of summary objects with the metrics listed above
- `skipped`: array of datasets omitted due to unsupported languages or transient issues

Reference results from a workstation run are stored in
[`data/benchmark_suite_results.json`](../data/benchmark_suite_results.json).

## Downloadable Datasets

All datasets resolve to public archives that can be mirrored locally. Checksums are
provided where available to simplify integrity validation. The manifest can also be
extended with additional corpora by appending new entries.
