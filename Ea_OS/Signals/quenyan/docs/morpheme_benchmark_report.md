# Benchmark Report: Quenya Morpheme Encoding vs. Alternatives (PROMPT 1.2.D)

The `scripts/run_benchmarks.py` harness evaluates the QYN-1 morpheme encoder against three
reference strategies on the six-line hypotenuse example used in the regression tests. Each scenario
was measured using the median of 10 micro-benchmarks. Raw results are stored in
[`benchmark_output.json`](../benchmark_output.json).

| Encoding strategy | Encode time (µs) | Decode time (µs) | Size before ANS (bytes) | Deterministic |
| --- | ---: | ---: | ---: | :---: |
| Quenya Morpheme | 119.6 | 95.1 | 100 | ✅ |
| AST Dict (Proto-like JSON) | 54.4 | 71.8 | 1 474 | ✅ |
| Opcode (Python `marshal`) | 1.4 | 1.8 | 419 | ✅ |
| S-expression JSON | 60.7 | 62.1 | 1 372 | ✅ |

## Analysis

* **Encoding/Decoding Speed:** The morpheme pipeline performs additional structural work to emit
  payload metadata and therefore trails the raw AST dump implementations. Even so, sub-0.12 ms
  median latency keeps the encoder suitable for IDE and CI workflows. Opcode serialisation is faster
  but tied to a single runtime and loses language-agnostic portability.
* **Compressed Size:** Prior to range-ANS compression the morpheme stream is 100 bytes compared with
  1.3–1.5 kB for the JSON-based formats. The fixed dictionary identifiers concentrate entropy and
  minimise payload chatter, making the subsequent ANS stage far more effective.
* **Determinism:** All approaches produced deterministic encodings in this benchmark, but only the
  morpheme stream exposes explicit dictionary and encoder versions for long-term reproducibility.
* **Extensibility:**
  * *Morpheme:* New constructs land by appending dictionary entries and adjusting payload schemas.
  * *Proto-like JSON:* Requires schema evolution machinery and tight coupling to specific AST field
    names per language.
  * *Opcode:* Effectively opaque; extending semantics demands new virtual machines or bytecode
    revisions.
  * *S-expression:* Flexible but verbose. Consumers must agree on field ordering conventions to
    avoid accidental drift.

In summary, the morpheme approach trades modest CPU overhead for vastly improved pre-compression
footprint, cross-language semantics, and explicit versioning—properties that are desirable for the
QYN-1 distribution format.
