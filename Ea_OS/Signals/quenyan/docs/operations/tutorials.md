# Operator Tutorials

Hands-on tutorials designed for engineers onboarding to the Quenyan pipeline.  Each scenario references the new CLI capabilities, project workflows, and KMS integrations.

## Tutorial 1 – First-Time Project Encode

1. **Prepare metadata**: ensure `${HOME}/.quenyan/aws-kms.json` contains the target key.
2. **Run the encoder**:
   ```sh
   mcs-reference project batch-encode \
     --passphrase "$QYN1_PASSPHRASE" \
     --project-root examples/python-service \
     --output-dir artifacts/python-service \
     --key-provider aws \
     --key-id alias/quenyan
   ```
3. **Inspect logs**: note the `project-batch-encode` event and verify integrations include `npm` if a `package.json` is present.
4. **Decode a sample**: `mcs-reference decode --passphrase "$QYN1_PASSPHRASE" --input artifacts/... --output demo.json`.

## Tutorial 2 – Incremental Build Maintenance

1. Seed a state file: `touch .ci/quenyan-state.json`.
2. Run the incremental workflow:
   ```sh
   mcs-reference project incremental-rebuild \
     --passphrase "$QYN1_PASSPHRASE" \
     --project-root repo/ \
     --output-dir repo/.artifacts \
     --state-file .ci/quenyan-state.json
   ```
3. Edit one descriptor and rerun the command; observe the `project-incremental-file` events showing `action: rebuilt`.
4. Review `.ci/quenyan-state.json` to understand the stored hashes and timestamps.

## Tutorial 3 – Dependency Graph Compliance Report

1. Generate the graph:
   ```sh
   mcs-reference project dependency-graph \
     --project-root repo/ \
     --json \
     --output compliance/dependency-graph.json
   ```
2. Load the JSON into your governance dashboard and cross-reference integrations with critical services.
3. Attach the report to the release ticket.

## Tutorial 4 – Key Rotation Drill

1. Execute a rotation:
   ```sh
   mcs-reference keys --provider local --key-id vault/key1 --rotate --json \
     --metadata-path ops/local-vault.json > rotation.json
   ```
2. Append the updated metadata to the descriptor of a test package and rerun `batch-encode`.
3. Confirm `decode` surfaces the new `key_management` block inside the metadata section.
4. Store `rotation.json` alongside incident logs.

## Tutorial 5 – Observability Quickstart

1. Launch a temporary Loki stack or log viewer.
2. Run `mcs-reference project batch-encode --log-format json ... | tee quenyan.log`.
3. Import `quenyan.log` into the viewer and filter on `event="key-metadata"`.
4. Create a dashboard summarising batch encode counts per project.

Practising these tutorials gives operators confidence before handling live deployments or audits.
