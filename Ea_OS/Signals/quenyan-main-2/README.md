# QYN-1 Reference Implementation

This repository contains a reference implementation of the Quenya Morphemic Crypto-Language (QYN-1) pipeline described in `quenyan_code_idea.txt`. The implementation provides:

* Deterministic canonicalisation of Python abstract syntax trees
* Encoding of canonical ASTs into Quenya-style morphemic tokens
* Table-based range ANS compression of the token stream with pluggable backends
* Authenticated encryption of the final package using ChaCha20-Poly1305 with
  metadata binding for tamper detection
* A command line interface for encoding, decoding, inspecting, and diffing encrypted packages
* A language-agnostic AST schema for representing cross-language constructs
* Frequency profiling tooling and benchmark harnesses for comparing compression options

## Command Line Usage

```
quenyan encode path/to/source.py --key .quenyan/keys/master.key -o build/source.qyn1
quenyan decode build/source.qyn1 --key .quenyan/keys/master.key -o build/source.py
quenyan verify build/source.qyn1 --key .quenyan/keys/master.key --check-signature --json
quenyan inspect build/source.qyn1 --show-metadata
quenyan diff old.qyn1 new.qyn1 --key .quenyan/keys/master.key
quenyan init --generate-keys --compression-mode=balanced
quenyan completion bash > ~/.local/share/bash-completion/quenyan
quenyan man

# Advanced tooling
quenyan encode-project dist/ path/to/a.py path/to/b.py --key .quenyan/keys/master.key --streaming-threshold=0 --json
quenyan encode-incremental build/mcs $(git ls-files '*.py') --key .quenyan/keys/master.key --cache-dir .qyn-cache --json
quenyan source-map build/source.qyn1 --key .quenyan/keys/master.key --output build/source.map --json
quenyan lint build/source.qyn1 --key .quenyan/keys/master.key
quenyan morphemes build/source.qyn1 --key .quenyan/keys/master.key --output build/source.trace
quenyan repo-pack manifests/project.json build/repo --archive build/repo.zip
quenyan repo-diff build/repo/index.json previous/index.json --json
```

Use `quenyan completion <shell>` to install shell completions, `quenyan man`
to view the packaged manual page, and `--help` on any command for detailed
usage. The CLI prints progress bars for large files and emits contextual error
messages with remediation tips.

The decoded source is emitted in canonical form using `ast.unparse`, which
removes formatting differences while preserving program semantics. See
`tests/test_roundtrip.py` for additional usage examples. The
`compression-backends` subcommand lists available ANS implementations and their
status on the current machine.


## Morpheme Dictionary and Encoding Pipeline

* The morpheme inventory with linguistic justification and compression metadata lives in [docs/quenya_morpheme_dictionary_v1.md](docs/quenya_morpheme_dictionary_v1.md).
* Composition and modifier grammar rules are captured in [docs/morpheme_composition_rules.md](docs/morpheme_composition_rules.md).
* Benchmark data comparing the morpheme stream to JSON and opcode encodings is summarised in [docs/morpheme_benchmark_report.md](docs/morpheme_benchmark_report.md).
* Cross-format compression ratios for 52 mixed-language projects are captured in [docs/compression_ratio_comparison.md](docs/compression_ratio_comparison.md) with raw figures in `data/compression_ratio_comparison.json`.
* Compression strategy trade-offs and the selected adaptive rANS approach are detailed in [docs/compression_strategy.md](docs/compression_strategy.md).
* Optional comment/docstring preservation is specified in [docs/metadata_preservation_strategy.md](docs/metadata_preservation_strategy.md).
* Source map semantics, encoding, and debugger usage are defined in [docs/source_map_spec.md](docs/source_map_spec.md).
* The full container layout is described in the [MCS Format v1.0 Specification](docs/mcs_format_v1_specification.md) together with the [extension mechanism](docs/mcs_extension_mechanism.md) and the [standardisation plan](docs/standardisation_plan.md).
* Language-neutral reference implementations live in `reference/python`, `reference/rust`, `reference/js`, and `reference/go`; each round-trips descriptors defined by the specification and emits the canonical binary payload.
* The CLI debugging suite is documented in [docs/debugging_tools.md](docs/debugging_tools.md).
* IDE integration strategy and the VS Code prototype are described in [docs/ide_integration.md](docs/ide_integration.md) with implementation under `ide/vscode/`.
* Cryptographic architecture, key hierarchy, and security testing guidance are provided in [docs/cryptographic_architecture.md](docs/cryptographic_architecture.md), [docs/encryption_mode_spec.md](docs/encryption_mode_spec.md), and [docs/security_audit_plan.md](docs/security_audit_plan.md). STRIDE analysis, deterministic encryption risks, third-party penetration testing, and frequency leakage research live in [docs/threat_model.md](docs/threat_model.md), [docs/deterministic_encryption_security_analysis.md](docs/deterministic_encryption_security_analysis.md), [docs/penetration_test_report.md](docs/penetration_test_report.md), and [docs/morpheme_information_leakage.md](docs/morpheme_information_leakage.md).
* Morpheme frequency histograms and usage guidance for training ANS models live in [docs/morpheme_frequency_report.md](docs/morpheme_frequency_report.md) with sample data under `data/morpheme_frequency_profile.json`.
* Language profile discovery, selection, and extension hooks are documented in [docs/language_profiles.md](docs/language_profiles.md).
* Incremental caching, distributed encoding, and CI integration guidance can be found in [docs/incremental_builds.md](docs/incremental_builds.md), [docs/distributed_encoding.md](docs/distributed_encoding.md), and [docs/ci_integration.md](docs/ci_integration.md).
* Repository packaging and diffing are documented in [docs/repository_format.md](docs/repository_format.md).
* The public benchmark suite, competitive comparisons, and optimisation notes are available in [docs/benchmark_suite.md](docs/benchmark_suite.md), [docs/competitive_benchmark_report.md](docs/competitive_benchmark_report.md), and [docs/optimization_log.md](docs/optimization_log.md). Stress and edge-case coverage is described in [docs/edge_case_testing.md](docs/edge_case_testing.md).
* Version headers, compatibility policy, and deprecation timelines are recorded in [docs/version_management.md](docs/version_management.md) alongside the stability SLAs in [docs/stability_policy.md](docs/stability_policy.md).

## Package Manager Integrations

* Node.js projects can use the helper under `integrations/npm/` to
  encode sources during `npm publish` and decode them automatically for
  local development.
* Python packages can integrate the custom `build_py` command from
  `integrations/python/quenyan_build.py` to emit `.qyn1` artefacts
  alongside wheels.

## Documentation Website

An MKDocs configuration under `docs/site/` powers the searchable
documentation portal with tutorials, conceptual guides, API references,
and example projects. Run `mkdocs serve -f docs/site/mkdocs.yml` to
preview the site locally.

## Profiling and Benchmarking Utilities

* `scripts/profile_morphemes.py` builds per-language morpheme histograms and entropy measurements for arbitrary corpora. See the documentation above for invocation patterns.
* `scripts/benchmark_compression.py` benchmarks each available compression backend and reports string table savings.
* `scripts/benchmark_performance.py` captures end-to-end throughput, gzip comparisons, AEAD speed, and streaming memory usage (outputs `data/performance_baseline.json`).
* `scripts/profile_pipeline.py` records cumulative function timings to highlight bottlenecks (outputs `data/pipeline_profile.json`).
* `scripts/run_benchmarks.py` retains the comparative encoding baseline between QYN-1 and alternative serialisation strategies.
* `scripts/run_benchmark_suite.py` drives the downloadable benchmark corpus and writes structured JSON summaries for dashboards.
* `scripts/benchmark_compression_ratio.py` summarises the 52-project compression comparison dataset and emits per-mode ratios.

## Universal AST Schema

The `docs/universal_ast.schema.json` file defines a canonical JSON schema capable of describing
abstract syntax trees for Python, JavaScript/TypeScript, Go, Rust, and C++. Accompanying
documentation in `docs/universal_ast_mapping.md` outlines node semantics, ordering rules, optional
field handling, and language-specific mapping examples.

Performance targets and the optimisation roadmap live in
[`docs/performance_requirements.md`](docs/performance_requirements.md) and
[`docs/performance_profiling.md`](docs/performance_profiling.md).
