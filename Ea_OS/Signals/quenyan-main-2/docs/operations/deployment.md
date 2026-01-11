# Deployment Playbooks

This guide captures the supported topologies and automation practices for deploying the Quenyan toolchain with the enhanced project workflows.

## 1. Reference Architecture

| Component | Responsibility | Notes |
| --- | --- | --- |
| `mcs-reference` CLI | Batch encoding, incremental rebuilds, dependency analysis | Ships with structured JSON logging controlled via `--log-format`. |
| Build system | Compiles or bundles source code prior to encoding | Integrations available for Cargo, npm, Maven, and Gradle. |
| KMS / Vault | Manages cryptographic keys and audit trails | Supported providers: AWS KMS, Azure Key Vault, secure local vault. |
| Observability stack | Collects CLI logs and exports metrics | JSON logs are fan-out friendly and include timestamps + event names. |

The CLI may be installed alongside build agents or on a dedicated packaging node.  When running alongside CI workers ensure `QYN1_PASSPHRASE` is injected as a masked secret.

## 2. Installing the CLI

1. Install Rust (if building from source) or download the binary release artifact.
2. Set the desired log format globally:
   ```sh
   mcs-reference --log-format json --help
   ```
3. Populate the KMS metadata store.  Example seed file for AWS KMS:
   ```json
   {
     "alias/quenyan": {
       "provider": "aws",
       "key_id": "alias/quenyan",
       "key_version": "5",
       "rotation_due": "2024-12-01T00:00:00Z",
       "state": "enabled",
       "alias": "alias/quenyan",
       "material_arn": "arn:aws:kms:eu-west-1:111122223333:key/abcd",
       "audit_trail": []
     }
   }
   ```
   Save the document to `${HOME}/.quenyan/aws-kms.json` or point the CLI at a custom path via `--key-metadata-path`.

## 3. Build System Integration

The `tools` module auto-detects common build manifests and exposes the results through the `project dependency-graph` command.  Example automation strategy:

1. Run the native build: `cargo build --workspace`.
2. Invoke batch encoding with KMS enrichment:
   ```sh
   mcs-reference project batch-encode \
     --passphrase "$QYN1_PASSPHRASE" \
     --project-root . \
     --output-dir target/quenyan-artifacts \
     --key-provider aws \
     --key-id alias/quenyan
   ```
3. Upload `target/quenyan-artifacts` to artifact storage.

Reference GitHub Actions workflows for each build system live in [`ci/pipelines`](../../ci/pipelines/).

## 4. Environment Configuration Matrix

| Setting | Description | Default |
| --- | --- | --- |
| `QYN1_PASSPHRASE` | Encryption passphrase used by the CLI | _required_ |
| `QYN1_KMS_DIR` | Override directory for KMS metadata stores | `$HOME/.quenyan` |
| `--log-format` | `json`, `plain`, or `quiet` logging | `json` |
| `--state-file` | Location for incremental build metadata | `.quenyan-state.json` (custom) |

## 5. Promotion Strategy

- **Development** – Run `incremental-rebuild` on each pull request to keep artifacts fresh while respecting the build cache.
- **Staging** – Execute `batch-encode` nightly and archive the logs for compliance.
- **Production** – Trigger `dependency-graph --json` once per release candidate; export the JSON to the governance portal and attach it to the release ticket.

## 6. Troubleshooting Checklist

1. **Missing artifacts** – Check the JSON logs for `project-incremental-file` events that list `action: rebuild`.
2. **KMS failures** – Ensure the metadata JSON includes the target `key_id`.  The CLI exits with a structured error if the key cannot be found.
3. **CI secret leakage** – Always pass the passphrase via environment variables; never write it to disk or logs.  The CLI logs omit secret material by design.

With these practices the Quenyan pipeline can be managed like any other production-grade build step while retaining cryptographic assurances.
