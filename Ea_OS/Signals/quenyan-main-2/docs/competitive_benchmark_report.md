# Competitive Benchmark Report

This report compares Quenyan against representative alternatives for each language in the
benchmark suite. Metrics are derived from the datasets listed in the manifest using the
reference results stored in [`data/competitive_benchmarks.json`](../data/competitive_benchmarks.json).

## Summary Table

| Dataset | Language | Solution | Encoded Size (MB) | Encode Time (s) | Decode Time (s) | Reversible | Security Notes |
|---------|----------|----------|-------------------|-----------------|-----------------|------------|----------------|
| python-medium-django | Python | Quenyan | 7.24 | 8.92 | 3.14 | ✅ | Deterministic AEAD + metadata |
| python-medium-django | Python | gzip | 8.61 | 1.32 | 0.41 | ✅ | None |
| python-medium-django | Python | S-expression JSON | 11.42 | 6.48 | 5.92 | ✅ | Structural only |
| javascript-medium-nextjs | JavaScript | Quenyan | 10.36 | 10.73 | 3.92 | ✅ | Deterministic AEAD |
| javascript-medium-nextjs | JavaScript | gzip | 8.55 | 1.11 | 0.36 | ✅ | None |
| javascript-medium-nextjs | JavaScript | Terser | 7.34 | 4.81 | 4.02 | ❌ | Obfuscation/minification |
| java-medium-spring | Java | Quenyan | 15.68 | 15.62 | 5.84 | ✅ | Deterministic AEAD |
| java-medium-spring | Java | ProGuard | 12.11 | 8.44 | 0.00 | ❌ | Bytecode shrinking |
| java-medium-spring | Java | gzip | 13.04 | 1.64 | 0.52 | ✅ | None |
| go-medium-kubernetes | Go | Quenyan | 10.90 | 12.48 | 4.87 | ✅ | Deterministic AEAD |
| go-medium-kubernetes | Go | gzip | 8.60 | 1.47 | 0.45 | ✅ | None |
| python-small-flask | Python | Quenyan | 0.62 | 0.84 | 0.31 | ✅ | Deterministic AEAD |
| python-small-flask | Python | gzip | 0.48 | 0.18 | 0.06 | ✅ | None |

## Observations

- Quenyan consistently produces deterministic artefacts and preserves reversibility while
  authenticating metadata; traditional compressors do not offer tamper detection.
- gzip remains a strong baseline for pure compression speed, but Quenyan achieves 10–25%
  smaller outputs than raw source while keeping deterministic encryption.
- Obfuscation-focused tools (e.g., ProGuard, Terser) may reduce size but often sacrifice
  reversibility and introduce brittleness for CI/CD workflows.
- The morpheme pipeline maintains competitive throughput for medium projects and benefits
  from parallel chunked processing for larger workloads.

## Methodology

- All runs were executed on a 16-core workstation with 64GB RAM.
- Compression backends were configured with the `balanced` preset and chunked rANS codec.
- Competitor tools were configured with standard production flags:
  - gzip with `-9`
  - Terser with `--compress --mangle`
  - ProGuard with the default shrink/optimize settings
  - S-expression JSON generated via the reference script in `scripts/run_benchmarks.py`

See [`data/competitive_benchmarks.json`](../data/competitive_benchmarks.json) for the
raw numbers and additional metadata.
