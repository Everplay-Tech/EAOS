# Repository-Level MCS Format

The repository format bundles encoded files, metadata, and content-addressed
objects so that large projects can be stored and diffed efficiently.

## Layout

```
repo/
  index.json
  mirror/
    src/app.py.qyn1
  objects/
    ab/cdef....qyn1
```

- `mirror/` mirrors the source tree with `.qyn1` suffixes for sparse checkout or
debugging.
- `objects/` stores encrypted packages addressed by SHA-256 hash to enable
  deduplication.
- `index.json` records the mapping between source paths and package hashes along
  with compression metadata.

## Building an Archive

```bash
python -m qyn1.cli repo-pack manifests/project.json build/repo \
  --archive build/project.mcs.zip
```

The manifest format references source files and their packages:

```json
{
  "root": "./",
  "entries": [
    {"source": "src/app.py", "package": "build/mcs/app.qyn1"}
  ]
}
```

`repo-diff` compares two `index.json` files and reports added, removed, and
changed entries without touching package payloads.
