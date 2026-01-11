#!/usr/bin/env bash
set -euo pipefail

# Use a local mirror when provided. Supported inputs:
# - CARGO_MIRROR_DIRECTORY: path to a `cargo vendor` directory.
# - CARGO_MIRROR_REGISTRY: full registry source string (e.g., registry+file://... or registry+https://...).
CONFIG_ARGS=()

if [[ -n "${CARGO_MIRROR_DIRECTORY:-}" ]]; then
  CONFIG_ARGS+=(--config "source.crates-io.replace-with=local-mirror")
  CONFIG_ARGS+=(--config "source.local-mirror.directory=${CARGO_MIRROR_DIRECTORY}")
elif [[ -n "${CARGO_MIRROR_REGISTRY:-}" ]]; then
  CONFIG_ARGS+=(--config "source.crates-io.replace-with=local-mirror")
  CONFIG_ARGS+=(--config "source.local-mirror.registry=${CARGO_MIRROR_REGISTRY}")
fi

if [[ ${#CONFIG_ARGS[@]} -gt 0 ]]; then
  export CARGO_NET_OFFLINE="${CARGO_NET_OFFLINE:-true}"
  export CARGO_REGISTRIES_CRATES_IO_PROTOCOL="${CARGO_REGISTRIES_CRATES_IO_PROTOCOL:-sparse}"
fi

cargo "${CONFIG_ARGS[@]}" test
