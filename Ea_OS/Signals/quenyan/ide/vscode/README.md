# QYN-1 VS Code Extension

The Quenyan VS Code extension provides a full development workflow for
`.qyn1` encrypted packages. It shells out to the CLI for heavy lifting
while presenting an IDE-native experience.

## Capabilities

- Automatic decoding of `.qyn1` files into temporary buffers with
  transparent re-encoding on save.
- Status bar indicator showing encryption state for the active editor.
- Key management commands to generate, import, and export passphrases.
- Source map export, metadata inspection, and package verification via
the command palette.
- Diff viewer for encrypted packages that decodes to temporary files
  before launching VS Code's diff UI.
- Syntax highlighting for morpheme streams and decrypted buffers.
- Integrated Quenyan terminal shortcut plus configuration options for
  custom CLI invocation and workspace key files.

## Getting started

1. Install the Quenyan CLI (`pip install .` from the repository root or
   use the published package).
2. Configure a key via the `QYN: Generate New Key` or `QYN: Import
   Existing Key` commands.
3. Open a `.qyn1` file and accept the prompt to decode it. Edits to the
   decrypted buffer will be re-encoded automatically.
4. Use the `QYN: Diff Packages`, `QYN: Verify Package Integrity`, and
   `QYN: Export Source Map` commands from the command palette as needed.

The extension stores passphrases using VS Code's secret storage and
respects workspace settings `quenyan.cliCommand` and `quenyan.keyFile`.
