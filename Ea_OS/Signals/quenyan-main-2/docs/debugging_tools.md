# QYN-1 Debugging Toolchain

## Overview

The reference CLI now includes a suite of utilities that enable developers to
inspect and operate on encrypted QYN-1 packages without compromising
confidentiality.

## Commands

| Command            | Purpose                                                            |
|--------------------|--------------------------------------------------------------------|
| `inspect`          | Read wrapper metadata (size, symbol count, dictionary version)     |
| `source-map`       | Export or summarise the embedded source map                        |
| `decompile`        | Produce canonical source code from an encrypted package            |
| `diff`             | Compare two packages at the morpheme level                         |
| `lint`             | Run static analysis on morpheme streams and metadata consistency   |
| `morphemes`        | Print or export the human-readable morpheme sequence               |

### Inspector

`python -m qyn1.cli inspect encrypted.qyn1 --json`

Outputs size and metadata without requiring a passphrase. Useful for
triage, inventory, and monitoring pipelines.

### Source Map Export

`python -m qyn1.cli source-map encrypted.qyn1 --passphrase pw --output file.map`

Writes the compressed source map to disk and prints a summary. Debuggers feed the
map directly to translate runtime tokens into source locations.

### Decompiler

`python -m qyn1.cli decompile encrypted.qyn1 --passphrase pw --output recovered.py`

Generates the canonicalised Python source. Combine with the metadata-preservation
API to rehydrate docstrings and comments where available.

### Diff and Lint

`python -m qyn1.cli diff a.qyn1 b.qyn1 --passphrase pw`

Returns a JSON document listing token deltas and payload counts. The linter checks
for unknown morphemes, missing source maps, and mismatched payload sizes; it exits
non-zero when issues are found.

## Debugger Integrations

- **pdb**: Load the source map via `source-map` and register a custom formatter
  that maps morpheme token indexes back to `(file, line)` using the JSON summary.
- **lldb / gdb**: Provide a Python bridge that calls the CLI to retrieve metadata
  and installs breakpoint translators.
- **IDE hooks**: The VS Code prototype (see `ide/vscode`) shells out to `qyn1.cli`
  commands to populate hover documentation and go-to-definition results.

Future work will extend the toolkit with comment/docstring lookups as soon as the
Context Ledger storage lands.
