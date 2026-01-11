# Incremental Encoding and Build Integration

The incremental encoder avoids recomputing packages for unchanged files by
hashing source content, tracking dependency digests, and persisting encrypted
packages in a local cache. A typical cache directory contains an `index.json`
file describing cache entries and a `packages/` directory with deduplicated
artifacts.

## Command Line Usage

```bash
python -m qyn1.cli encode-incremental build/mcs src/app.py src/lib.py \
  --passphrase "$PASSPHRASE" \
  --cache-dir .qyn-cache \
  --manifest config/dependencies.json \
  --json
```

The command prints a JSON summary containing cache hit statistics that can be
fed into CI dashboards. Sharding options (`--shard-index`/`--shard-count`)
permit horizontal scaling across CI runners.

## Dependency Manifests

Dependencies can be declared in a JSON file consumed via `--manifest`:

```json
{
  "src/app.py": ["src/lib.py"],
  "src/lib.py": []
}
```

When a dependency changes, its dependants are invalidated automatically. The
encoder also performs best-effort Python import analysis and merges it with the
manifest data.

## Cache Layout

- `index.json` – cache metadata including hashes and dependency digests.
- `packages/` – content-addressed encrypted files keyed by SHA-256 hash.

The cache is safe to share between CI workers on network storage. Index updates
use atomic file replacements to avoid race conditions.
