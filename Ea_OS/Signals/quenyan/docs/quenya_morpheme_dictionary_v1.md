# QYN-1 Morpheme Dictionary (Version 1.0)

The canonical Quenya morpheme dictionary that drives the QYN-1 encoder contains **230 entries**
covering core programming constructs, data types, operators, control-flow primitives, object-
oriented structures, structural markers, and metadata sentinels. The machine-readable source is
published alongside the library at [`resources/morpheme_dictionary_v1/dictionary.json`](../resources/morpheme_dictionary_v1/dictionary.json).
published alongside the library at [`qyn1/resources/morpheme_dictionary/v1_0/dictionary.json`](../qyn1/resources/morpheme_dictionary/v1_0/dictionary.json).
Each entry documents the following attributes:

| Field | Description |
| --- | --- |
| `key` | Stable identifier used by the encoder/decoder (e.g. `construct:function`). |
| `morpheme` | The Quenya phoneme emitted in the morpheme stream. |
| `quenya_root` | Canonical root that anchors the morpheme etymology. |
| `gloss` | Literal gloss that motivates the semantic mapping. |
| `linguistic_justification` | Narrative linking the Quenya root to the programming construct. |
| `ast_nodes` | Representative AST node kinds or constructs that map to the entry. |
| `frequency_per_10k_loc` | Estimated occurrences per 10 kLOC used to weight compression. |
| `encoding` | Binary encoding shape (`fixed` or `prefix`) with bit-width metadata. |

## Coverage Overview

The table below summarises the major bands of the dictionary. Individual entries are grouped by
the `key` prefix; each row lists the count of morphemes present in that slice.

| Category prefix | Examples | Count |
| --- | --- | ---: |
| `construct:` | `construct:function`, `construct:while`, `construct:try` | 35 |
| `type:` | `type:int`, `type:map`, `type:promise` | 30 |
| `op:` | `op:add`, `op:await`, `op:nullish_assign` | 38 |
| `flow:` | `flow:return`, `flow:panic`, `flow:checkpoint` | 24 |
| `oop:` | `oop:class`, `oop:virtual_method`, `oop:record` | 25 |
| `modifier:` | `modifier:async`, `modifier:sealed`, `modifier:invariant` | 30 |
| `literal:` | `literal:int`, `literal:regex` | 10 |
| `structure:` | `structure:identifier`, `structure:generic`, `structure:spread` | 20 |
| `meta:` | `meta:stream_start`, `meta:dictionary_version`, `meta:unknown` | 10 |

## Sample Entries

| Key | Morpheme | Quenya root | AST mapping | Frequency/10k | Encoding |
| --- | --- | --- | --- | ---: | --- |
| `construct:function` | `kar` | `kar-` (“to make or do”) | Python `FunctionDef`, Rust `FnItem` | 2400 | `fixed` 9-bit `000000000` |
| `construct:if` | `ce` | `ce-` (“if, maybe”) | `IfStatement`/`ConditionalExpression` | 2379 | `fixed` 9-bit `000000110` |
| `type:float` | `linga` | `linga-` (“to float or hang”) | Python `float`, C++ `double` | 2293 | `fixed` 9-bit `000010100` |
| `op:mul` | `yulma` | `yul-` (“to mix”) | Binary `*` | 2265 | `fixed` 9-bit `000011001` |
| `flow:defer` | `hantale` | `hantalë-` (“later gratitude”) | Go `defer`, Rust `DropGuard` | 2113 | `prefix` `10` + 12 payload bits |
| `oop:sealed` | `hresta` | `hresta-` (“shore boundary”) | C# sealed classes, Kotlin sealed hierarchies | 2065 | `prefix` `10` + 12 payload bits |
| `modifier:noexcept` | `úcare` | `úcarë-` (“without error”) | C++ `noexcept` specifier | 2013 | `prefix` `10` + 12 payload bits |
| `literal:regex` | `lindë` | `lindë-` (“song pattern”) | JavaScript regex literal | 1965 | `prefix` `10` + 12 payload bits |
| `structure:spread` | `palya` | `palya-` (“to spread”) | JS spread / Python `*` unpack | 1937 | `prefix` `10` + 12 payload bits |
| `meta:stream_end` | `mettar` | `mettar-` (“ending day”) | Stream terminator sentinel | 1806 | `prefix` `110` + 15 payload bits |

The JSON file is sorted in descending frequency order to make compression table construction
stable and deterministic. Low-frequency morphemes (rank ≥ 193) use an `110` prefix followed by a
15-bit payload, leaving headroom for future growth without disturbing existing assignments.

## Extending the Dictionary

* **Versioning:** Additional dictionaries should be stored in `qyn1/data/` as
  `morpheme_dictionary_v{major.minor}.json` and registered in `qyn1/dictionary._DATA_FILES`.
* **Linguistic fidelity:** New morphemes must cite a Quenya root with a gloss that motivates the
  programming concept. The justification string should be written in natural language.
* **Compression tuning:** Update `frequency_per_10k_loc` based on corpus analysis so that range-ANS
  tables continue to favour the most common constructs.
* **Testing:** Add regression samples to ensure new entries round-trip through the encoder/decoder
  and update documentation tables when category counts shift.
