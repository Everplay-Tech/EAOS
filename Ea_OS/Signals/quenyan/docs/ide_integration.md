# IDE Integration Strategy

## Architecture

1. **Language Server Adapter** – A lightweight shim that hosts the canonical
   language server (e.g., Python's `pyright` or Typescript's `tsserver`) and
   proxies requests through the QYN-1 toolchain.
2. **Secure Workspace Cache** – Decrypted source is stored in a transient memory
   buffer encrypted-at-rest using the project key. Files are decrypted on demand
   and wiped after inactivity.
3. **Metadata Prefetcher** – Fetches Context Ledger entries (docstrings,
   comments, formatting hints) without touching morpheme tokens.
4. **Source Map Resolver** – Translates editor cursor positions to morpheme
   token indexes for breakpoint placement and stack trace visualisation.
5. **Audit Logger** – Records decryption events and metadata reads for security
   auditing.

## Workflow

1. IDE requests a document via LSP.
2. Adapter invokes `qyn1.cli decompile` to obtain canonical source plus metadata
   enrichment. Source is cached in the secure workspace.
3. Hover tooltips and docstrings come from the metadata prefetcher; no additional
   decryptions are performed.
4. Breakpoints use the source map resolver to map `(line, column)` to morpheme
   tokens and are stored alongside debugging sessions.
5. The audit logger writes structured events (who, what file, when) to the team
   monitoring system.

## VS Code Prototype

Located in `ide/vscode/`, the prototype extension demonstrates the flow:

- Activates on `.qyn1` files.
- Invokes `qyn1.cli inspect` and `qyn1.cli decompile` to populate a virtual
  document with decrypted content.
- Provides commands:
  - `QYN: Inspect Package Metadata`
  - `QYN: Export Source Map`
- Stores decrypted buffers in a temporary file encrypted with a session key.

The extension is intentionally minimal but verifies the handshake between VS Code
and the CLI, laying the groundwork for richer features (autocomplete, linting,
inline documentation) once the metadata preservation API ships.
