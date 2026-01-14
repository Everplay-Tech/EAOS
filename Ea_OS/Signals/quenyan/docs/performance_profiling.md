# Profiling Report and Optimisation Plan

The profiling harness (`scripts/profile_pipeline.py`) captures cumulative
function timings while running the encoder → compressor → encryptor stack on a
representative module. The latest run highlights the following hotspots:

| Rank | Function | Cumulative Time (s) |
| ---- | -------- | ------------------ |
| 1 | `scripts/profile_pipeline.py:run_workload` | 0.251 |
| 2 | `qyn1/package.py:to_bytes` | 0.225 |
| 3 | `qyn1/crypto.py:_chacha20_poly1305_encrypt` | 0.172 |
| 4 | `qyn1/encoder.py:encode` | 0.038 |
| 5 | `qyn1/compression.py:ChunkedRANSBackend.encode` | 0.032 |

Full profiler output is versioned in `data/pipeline_profile.json` for deeper
inspection.【F:data/pipeline_profile.json†L1-L15】 The results show that
encryption dominates runtime, closely followed by package serialisation and the
chunked ANS backend.

## Identified Bottlenecks

1. **Encryption (`crypto._chacha20_poly1305_*`)** – pure Python ChaCha20 is slow
   and currently takes ~69% of the total runtime. Hardware acceleration via
   libsodium or PyNaCl would cut this dramatically.
2. **Package serialisation (`package.to_bytes`)** – spends time JSON encoding and
   base64 wrapping large buffers. Streaming the payload to a binary container or
   reusing preallocated buffers would reduce allocations.
3. **Chunked ANS encoding** – incurs per-chunk frequency table builds. SIMD or
   a Rust extension would raise throughput.
4. **AST traversal (`encoder.encode`)** – benefits from parallel fan-out across
   files; the new `encode_project` helper already distributes work across CPU
   cores and uses disk-backed token buffers to cap memory pressure.【F:qyn1/pipeline.py†L1-L170】

## Optimisation Roadmap

* **Short term** – exploit the new multi-process encoder for project builds and
  adopt the streaming `chunked-rans` backend for files that exceed the
  configurable threshold. This amortises the AST traversal cost across workers
  while keeping per-process memory <100 MB.
* **Medium term** – replace the pure Python ChaCha20 implementation with a
  bindings-backed alternative (libsodium or OpenSSL) and cache per-language ANS
  tables to reduce the per-chunk frequency rebuilds.
* **Long term** – migrate the encoder’s inner loops (token emission and chunk
  assembly) to Cython or Rust to reach the throughput targets documented in
  `docs/performance_requirements.md`.

The streaming encoder and parallel pipeline added in this change lay the
foundation for these next steps by isolating token buffers, exposing chunk-level
metadata, and making the concurrency model explicit.

## Container-Level Tuning

The profiling data shows that CPU-bound encryption and package serialisation
dominate runtime, so container-level limits directly impact headroom for those
hot paths.【F:data/pipeline_profile.json†L1-L15】 Apply the following operating
constraints when running the CLI in build agents or shared runners:

- **Pin CPU and memory reservations to the encoder profile** – allocate at least
  2 vCPUs and 512 MB RAM per concurrent worker so ChaCha20 and the ANS backend
  avoid throttling when processing large batches.
- **Prefer dedicated cgroups for background I/O** – place download/extract
  helpers in a lower-priority slice to keep the encoder and encryptor on latency
  friendly cores.
- **Mount a tmpfs scratch volume for chunk buffers** – keeps the chunked rANS
  backend from contending with networked filesystems, stabilising the
  compression timing variance seen in the baseline run.
- **Enable deterministic clock sources in containers** – set `CLOCK_MONOTONIC`
  and disable frequency scaling so cross-run throughput comparisons remain
  comparable when regression testing performance fixes.

These settings preserve the measured balance between encryption, container
serialisation, and chunk compression while preventing cgroup pressure from
masking regressions.

## Project-Level Priors by Language and Domain

Use the performance breakdown to seed priors for the encoder presets when
onboarding new projects. The goal is to align chunk sizing, concurrency, and
compression hints with typical hotspot distributions while keeping outputs
deterministic.【F:data/pipeline_profile.json†L1-L15】

- **Python web services** – favour smaller chunk sizes (64–96 KiB) to smooth
  docstring-heavy modules and templates; keep 3–4 workers to avoid oversubscribing
  the GIL-bound AST parsing stages while still overlapping encryption.
- **Python data/ML workloads** – increase chunk sizes (128–192 KiB) so large
  numeric literals and generated code amortise frequency-table rebuilds; enable
  the streaming encoder to bound RSS when processing notebooks and checkpoints.
- **JavaScript frontend bundles** – enable aggressive parallelism (one worker
  per 1–1.5 vCPU) because parsing/minification steps are already chunked by
  bundlers; bias the ANS backend toward balanced mode to control size bloat from
  vendor bundles.
- **Node.js services** – align chunk sizes with deployment artefacts (~128 KiB)
  and pre-cache morpheme tables for common library code so cold-start latency in
  containerised runtimes stays predictable.
- **Rust / C++ macro-heavy builds** – prefer more workers with moderate chunk
  sizes (96–128 KiB) to distribute macro expansion hotspots while keeping the
  chunked rANS encoder fed; pin the encryptor to a dedicated core to prevent
  CPU-bound ChaCha20 from stalling macro parsing.
- **Rendering / graphics engines (Rust/C++)** – prioritise peak throughput by
  using larger chunks (192–256 KiB) and preallocating token buffers in tmpfs to
  handle asset-heavy pipelines without spiking metadata overhead.

These priors should be recorded alongside project manifests so CI runners can
apply tuned defaults without manual flags. The `scripts/run_benchmark_suite.py`
reporting harness can validate that the tuned settings still conform to the
baseline ratios before promoting them to production presets.
