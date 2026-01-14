# Your First Quenyan Project in 10 Minutes

This hands-on tutorial walks you through encoding a Python service into
Quenyan packages and running automated verification inside CI.

## Prerequisites

- Python 3.10+
- Quenyan CLI (`pip install qyn1`)
- Git for version control

## 1. Scaffold the workspace

```bash
mkdir hello-quenyan
cd hello-quenyan
python -m venv .venv
source .venv/bin/activate
pip install qyn1
quenyan init --generate-keys
```

## 2. Write a simple service

```python
# app.py
def greet(name: str) -> str:
    return f"Suilad, {name}!"
```

## 3. Encode the source

```bash
quenyan encode app.py --key .quenyan/keys/master.key --human-readable app.trace
```

The command prints progress bars for large files and writes
`app.qyn1` alongside the trace file.

## 4. Verify determinism

```bash
quenyan verify app.qyn1 --key .quenyan/keys/master.key --check-signature
```

## 5. Integrate with CI

Add the following to `.github/workflows/encode.yml`:

```yaml
- name: Encode sources
  run: |
    pip install qyn1
    quenyan encode-project build/qyn src/**/*.py --key .quenyan/keys/master.key --json
```

## 6. Recover source locally

```bash
quenyan decode build/qyn/app.qyn1 --key .quenyan/keys/master.key -o restored.py
```

You're now ready to explore incremental builds, distributed encoding,
and IDE tooling for your encrypted project.

## Managing encryption keys safely

Deterministic pipelines should record key rotations explicitly. The
reference Rust CLI ships with a helper for tracking project-level key
material:

```bash
mcs-reference keys roll \
  --project hello-quenyan \
  --state .quenyan/keys/rotation.json \
  --created "$SOURCE_DATE_EPOCH"
```

The command increments the rotation generation, emits a fresh project
salt, and persists it in the state file. Include the state file in
version control so subsequent builds reuse the same rotation metadata.

When encrypting artefacts you can reuse the recorded state and feed in
deterministic provenance:

```bash
mcs-reference encrypt \
  --passphrase "$QUENYAN_MASTER" \
  --project hello-quenyan \
  --file app.py \
  --rotation-state .quenyan/keys/rotation.json \
  --provenance-manifest build/provenance.json \
  --provenance-input compiler=rustc1.78
```

`mcs-reference` defaults the `created` field to either
`SOURCE_DATE_EPOCH`, `GIT_COMMIT_TIMESTAMP`, or the rotation timestamp.
Provide explicit `--salt` and `--nonce` values (base64 encoded) if you
need byte-for-byte reproducibility; the CLI will reject reuse unless a
nonce registry vouches for uniqueness.
