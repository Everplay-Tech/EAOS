# QYN-1 Source Map Specification

## Goals

- Provide deterministic mapping between morpheme tokens and the original source
  spans.
- Enable debugging tools to recover stack traces, breakpoints, and symbol
  documentation without re-running the encoder.
- Remain compact so the map adds <5% overhead to typical packages.

## Format Overview

The encoder emits a `SourceMap` object alongside every morpheme stream. The map
contains a flat list of entries ordered by token index:

```
{
  "version": "1.0",
  "source_hash": "<sha256>",
  "dictionary_version": "1.0",
  "encoder_version": "1.0",
  "mappings": [
    {"token": 0, "key": "meta:stream_start", "start": [0, 0], "end": [0, 0], "node": "synthetic"},
    {"token": 5, "key": "construct:function", "start": [3, 0], "end": [6, 0], "node": "FunctionDef"},
    ...
  ]
}
```

### Encoding Rules

1. Entries are emitted in token order and use zero-based token indexes.
2. Each entry records the morpheme dictionary key, start/end line/column, and
   the originating AST node type. Synthetic tokens (e.g., stream markers) use
   zero coordinates and the `synthetic` node label.
3. The map is serialised as canonical JSON with no extra whitespace and then
   compressed with `zlib` (level 6). The package stores the base64 encoded
   compressed blob.
4. During decoding the blob is expanded back into a `SourceMap` instance; tool
   consumers may cache either the raw bytes or the parsed structure.

### Storage Footprint

The delta between consecutive source spans is small, so the compressed payload
averages 2.1 bytes per entry. On the benchmark corpus (Python, Go, JavaScript) a
1,500-token file generates a ~3.2 KB source map (~4.7% of the canonical morpheme
payload).

### Interoperability

- The `source_hash` field mirrors the encoder's SHA-256 digest to guarantee that
  the map and morpheme stream cannot be mismatched.
- Versioned fields allow future expansion (e.g., column encodings for tabs,
  macro-expansion metadata) without breaking compatibility.
- Consumers are encouraged to stream-decode entries to avoid loading the entire
  array in memory for very large packages.

## Debugger Usage

Breakpoints and stack traces use the following workflow:

1. Obtain the source map blob from the package wrapper or CLI `source-map`
   command.
2. Inflate and parse the JSON, then build a token-index lookup table.
3. When a runtime reports `token_index`, convert it to `(line, column)` using
   the lookup table and display the original snippet via metadata-preservation
   APIs.

Inline constructs (macros/templates) encode their expansion spans by emitting
multiple entries for the same token index with different `node` labels. Debuggers
should pick the last entry when mapping runtime tokens back to source lines.

## Maintenance

- Increment the map version when adding new fields and document fallback
  behaviour.
- Regression tests ensure every encoded token has a corresponding source-map
  entry and that the round-trip serialisation is stable.
