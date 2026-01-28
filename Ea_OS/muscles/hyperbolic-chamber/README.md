# enzyme-installer

Adaptive, cross-platform installer CLI that turns declarative manifests into deterministic installation plans for macOS, Windows, and Linux machines.

## Features

- Environment detection that captures OS family/version, CPU architecture, RAM, common package managers, and a machine fingerprint for license hooks.
- Manifest-driven planning with deterministic mode selection and clear failure reasons.
- Plan execution via platform-appropriate shells with streaming stdout/stderr and rich step primitives.
- Extensible data model with downloads, archive extraction, and templated config rendering.
- Persistent install-state tracking so you can see what was attempted on the machine.
- **Enterprise features**: structured logging, audit trails, security controls, progress indicators, retry logic, and rollback/uninstall support.

## Getting started

### Build

```bash
cargo build --release
```

### Test

Run the validation and planner unit tests to ensure parsing and compatibility logic remain sound:

```bash
cargo test
```

### Commands

- Detect the current machine profile:

```bash
enzyme-installer detect
```

- Produce an installation plan without executing steps:

```bash
enzyme-installer plan examples/keanu.manifest.json
```

- Execute an installation plan end-to-end:

```bash
enzyme-installer install examples/keanu.manifest.json
```

- View recorded installs on this machine:

```bash
enzyme-installer list-installed
```

- Uninstall a previously installed application:

```bash
enzyme-installer uninstall <app-name> [--version <version>] [--dry-run]
```

Pass `--json` to any subcommand to receive machine-readable output (errors included). JSON payloads are emitted to stdout.

### Command-Line Options

- `--json` - Emit JSON output instead of human-readable text
- `--dry-run` - Show what would be executed without actually running commands (for `install` and `uninstall`)
- `--log-level <level>` - Set logging level: `trace`, `debug`, `info`, `warn`, `error` (default: `info`)
- `--log-file <path>` - Write logs to a file instead of stderr

## Manifest shape

Manifests describe a single application with multiple installation modes. Each mode declares requirements and per-OS steps for macOS, Windows, or Linux. See `examples/keanu.manifest.json` for a concrete example.

Supported steps:

- `{"run": "echo hi"}` – executes the command in a platform-appropriate shell (detects user's shell on Linux).
- `{"download": {"url": "https://example.com/file", "dest": "artifacts/file.zip", "expected_sha256": "...", "expected_size": 12345, "timeout_secs": 60}}` – downloads a file to the provided relative path with optional verification and timeout.
- `{"extract": {"archive": "artifacts/file.zip", "dest": "workdir"}}` – extracts an archive into the destination directory. Supports:
  - `.zip` files
  - `.tar` files
  - `.tar.gz` / `.tgz` files
  - `.tar.bz2` files
  - `.tar.xz` files
  - Standalone `.gz` files
- ```json
  {
    "template_config": {
      "source": "config/app.env.template",
      "dest": "workdir/.env",
      "vars": { "APP_NAME": "demo", "PORT": "3000" }
    }
  }
  ```
  Renders a text template by substituting `{{VAR}}` placeholders with provided values.

Existing manifests that only contain `run` steps continue to work without modification.

Linux targets can now sit alongside macOS and Windows modes. A simplified example shows the shape:

```json
{
  "modes": {
    "full": {
      "requirements": { "os": ["linux>=5"], "cpu_arch": ["x64", "arm64"] },
      "steps": {
        "linux": [
          { "run": "sudo apt-get update" },
          { "run": "sudo apt-get install -y postgresql nodejs npm" },
          { "run": "cd keanu && npm install && npm run build" }
        ]
      }
    }
  }
}
```

### Virtual runtimes (v3)

Each mode can declare a `runtime_env` describing an isolated runtime to prepare before running steps. The feature is additive and optional:

```json
{
  "modes": {
    "full": {
      "runtime_env": {
        "type": "node_local",
        "root": ".enzyme_env",
        "node": {
          "version": "20.11.0",
          "install_strategy": "local_bundle_or_global"
        }
      },
      "steps": {
        "macos": [ {"run": "node --version"} ],
        "linux": [ {"run": "node --version"} ]
      }
    },
    "light": {
      "runtime_env": {
        "type": "python_venv",
        "root": ".enzyme_env",
        "python": {
          "version": "3.11",
          "install_strategy": "venv_or_global"
        }
      },
      "steps": {
        "macos": [ {"run": "python -m pip --version"} ],
        "linux": [ {"run": "python -m pip --version"} ]
      }
    }
  }
}
```

- `node_local` prepares a per-app Node.js directory under `root/node` and prefers a locally provisioned binary. If none is present, the installer falls back to a compatible global `node` when allowed by `install_strategy`.
- `python_venv` creates a virtual environment at `root/venv` using a version-checked interpreter. When a `python.version` is provided, the installer trims whitespace, probes candidates with `python -V` before venv creation, prefers a managed runtime under `root/python/runtime`, and respects `install_strategy`: `local_only` requires a bundled or explicitly provided interpreter, while `venv_or_global` will reuse a compatible global Python. If every discovered interpreter is incompatible, installation fails immediately with a list of observed versions. Setting `ENZYME_PYTHON_RUNTIME` allows supplying a local Python binary to satisfy version pinning when no compatible interpreter is installed.

### Fingerprints

Environment detection now surfaces a fingerprint containing OS, version, architecture, RAM, hostname (when available), and a stable SHA-256 hash over those fields. Use `enzyme-installer detect --json` to inspect the structure when integrating licensing or per-machine bundle logic.

## Install state and reporting

Successful and failed installs are recorded per app version and mode. State is stored at:

- macOS: `$HOME/Library/Application Support/enzyme-installer/state.json`
- Windows: `%APPDATA%\enzyme-installer\state.json`
- Linux: `$XDG_DATA_HOME/enzyme-installer/state.json` (defaults to `$HOME/.local/share/enzyme-installer/state.json`)

Use `enzyme-installer list-installed` (or `--json` for structured output) to view historical records. Each record includes the app name, version, mode, OS, CPU architecture, status, timestamp, and artifacts created during installation.

### Uninstalling

The `uninstall` command removes previously installed applications and their artifacts:

```bash
# Uninstall all versions of an app
enzyme-installer uninstall my-app

# Uninstall a specific version
enzyme-installer uninstall my-app --version 1.0.0

# See what would be removed without actually removing it
enzyme-installer uninstall my-app --dry-run
```

The uninstaller removes:
- Downloaded files
- Extracted directories
- Created configuration files
- Runtime environments created during installation

## JSON output

All subcommands accept `--json` to emit a single JSON object to stdout. On failure, an error object is returned instead of human text. Examples:

- `enzyme-installer detect --json` → `{ "ok": true, "environment": { ... } }`
- `enzyme-installer plan manifest.json --json` → `{ "ok": true, "plan": { ... } }` or `{ "ok": false, "error": { "message": "...", "details": ["..."], "environment": { ... } } }`
- `enzyme-installer install manifest.json --json` → success response includes the plan and step counts; failures include the plan (when available) and the zero-based `failed_step_index`.
- `enzyme-installer list-installed --json` → `{ "ok": true, "installs": [ ... ] }`
- `enzyme-installer uninstall app-name --json` → `{ "ok": true, "removed_installs": 1, "removed_artifacts": 3 }`

## Enterprise Features

### Structured Logging

Use `--log-level` to control verbosity and `--log-file` to write logs to a file:

```bash
enzyme-installer install manifest.json --log-level debug --log-file install.log
```

Logs include structured fields like `step_index`, `command`, `app_name`, etc., making them easy to parse and analyze.

### Audit Trail

All operations are logged to an audit trail file:

- macOS/Linux: `~/.local/share/enzyme-installer/audit.log`
- Windows: `%APPDATA%\enzyme-installer\audit.log`

Each entry includes:
- Timestamp
- User who ran the command
- Command executed
- Manifest path (if applicable)
- App name and version
- Result (success/failure)
- Error messages (if any)

### Security Features

#### URL Allowlist/Blocklist

Create a security configuration file at:
- macOS/Linux: `~/.config/enzyme-installer/security.toml`
- Windows: `%APPDATA%\enzyme-installer\security.toml`

Example:

```toml
# Allow only specific domains
url_allowlist = [
    "https://example.com/*",
    "https://github.com/*"
]

# Block specific domains
url_blocklist = [
    "http://malicious-site.com/*"
]
```

URL patterns support `*` wildcards. If an allowlist is specified, only URLs matching patterns in the allowlist are allowed. Blocklist patterns take precedence over allowlist patterns.

#### Manifest Signatures

Manifests can include an optional `signature` field for Ed25519 signature verification:

```json
{
  "name": "my-app",
  "version": "1.0.0",
  "signature": "base64-encoded-ed25519-signature",
  "modes": { ... }
}
```

Signature verification is performed automatically when a signature is present. The installer uses Ed25519 cryptographic signatures to verify manifest authenticity.

**How it works:**
1. When a manifest includes a `signature` field, the installer loads trusted public keys from the security configuration file
2. The signature (base64-encoded, 64 bytes) is verified against the raw JSON manifest content
3. The installer tries each configured public key until one successfully verifies the signature
4. If no key verifies the signature, installation fails with a clear error message

**Setting up signature verification:**

1. Create a security configuration file at:
   - macOS/Linux: `~/.config/enzyme-installer/security.toml`
   - Windows: `%APPDATA%\enzyme-installer\security.toml`

2. Add your trusted public keys:
   ```toml
   public_keys = [
       "base64-encoded-ed25519-public-key-32-bytes",
       "another-trusted-key-if-needed"
   ]
   ```

3. Generate a keypair and sign your manifest:
   ```bash
   # Using openssl or similar tool to generate Ed25519 keypair
   # Sign the manifest JSON content with your private key
   # Add the base64-encoded signature to the manifest
   ```

**Troubleshooting signature verification:**

- **"no security configuration found"**: Create `security.toml` in the config directory with at least one `public_keys` entry
- **"no trusted public keys configured"**: Add at least one public key to the `public_keys` array in `security.toml`
- **"signature verification failed"**: The signature doesn't match any trusted public key, or the manifest content was modified after signing
- **"invalid signature length"**: Signature must be exactly 64 bytes (base64-encoded Ed25519 signature)
- **"invalid public key length"**: Public keys must be exactly 32 bytes (base64-encoded Ed25519 public key)

**Note**: Manifests without signatures are still accepted (backward compatible). Signature verification only occurs when a `signature` field is present.

### Progress Indicators

Downloads show progress bars with:
- Bytes downloaded / total bytes
- Percentage complete
- Download speed (MB/s)
- Estimated time remaining (ETA)

### Retry Logic

Network operations automatically retry on:
- Timeouts
- Connection errors
- 5xx server errors

Retries use exponential backoff (1s, 2s, 4s, 8s) with a maximum of 3 attempts. Client errors (4xx) are not retried.

### Error Reporting

Failed commands include:
- Full command output (stdout and stderr)
- Step index and description
- Environment context
- Detailed error messages

## Extensibility

The codebase intentionally isolates manifest parsing, environment detection, planning, execution, and persistence. New step types or requirement kinds can be added without breaking existing manifests or CLI contracts.

## Manifest Schema

A JSON Schema for manifests is available at `schema/enzyme-manifest.schema.json`. Use it to validate manifests in your CI/CD pipeline or editor.

## Troubleshooting

### Installation fails with "No compatible mode found"

Check the requirements in your manifest match your environment:
- OS version constraints (e.g., `linux>=5`)
- CPU architecture (`x64`, `arm64`, `x86`)
- RAM requirements (`ram_gb`)

Use `enzyme-installer detect` to see your current environment.

### Downloads fail

- Check your network connection
- Verify URLs are accessible
- Check security configuration (allowlist/blocklist)
- Review logs with `--log-level debug`

### Archive extraction fails

- Verify the archive format is supported (zip, tar, tar.gz, tar.bz2, tar.xz)
- Check file permissions
- Ensure sufficient disk space

### Shell commands fail on Linux

The installer detects your shell from `$SHELL` environment variable, falling back to `/bin/bash` or `/bin/sh`. Ensure your shell is compatible with the commands in your manifest.

## License

[Add your license here]
