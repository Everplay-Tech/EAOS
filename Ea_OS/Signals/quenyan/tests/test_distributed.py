from __future__ import annotations

from pathlib import Path

from qyn1.distributed import (
    build_distributed_plan,
    estimate_cluster_throughput,
    load_shard_manifest,
    write_plan_manifests,
)


def test_distributed_plan_round_trip(tmp_path) -> None:
    sources = [tmp_path / f"file_{index}.py" for index in range(5)]
    for path in sources:
        path.write_text("print('hi')\n", encoding="utf-8")
    plan = build_distributed_plan(
        sources,
        shards=3,
        cache_root=tmp_path / "cache",
        compression_mode="balanced",
        backend="rans",
    )
    manifest_dir = tmp_path / "manifests"
    write_plan_manifests(plan, tmp_path, manifest_dir)
    shard_manifest = load_shard_manifest(tmp_path, manifest_dir / "shard_0.json")
    assert shard_manifest.total == 3
    assert shard_manifest.sources
    metrics = estimate_cluster_throughput([1.5, 1.2, 1.1], shard_duration=1.6)
    assert metrics["speedup"] > 0.0
    assert metrics["efficiency"] > 0.0
