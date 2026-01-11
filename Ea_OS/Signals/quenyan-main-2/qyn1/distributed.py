"""Distributed encoding planning for large monorepos."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class ShardDescriptor:
    """Description of a single shard in a distributed encoding run."""

    index: int
    total: int
    sources: List[Path]

    def to_dict(self, root: Path) -> Dict[str, object]:
        return {
            "index": self.index,
            "total": self.total,
            "sources": [str(path.resolve().relative_to(root)) for path in self.sources],
        }


@dataclass(frozen=True)
class DistributedEncodingPlan:
    """Manifest describing how to distribute encoding work across workers."""

    shards: List[ShardDescriptor]
    compression_mode: str
    backend: str
    cache_root: Path

    def to_dict(self, root: Path) -> Dict[str, object]:
        return {
            "compression_mode": self.compression_mode,
            "backend": self.backend,
            "cache_root": str(self.cache_root.resolve()),
            "shards": [shard.to_dict(root) for shard in self.shards],
        }


def build_distributed_plan(
    sources: Sequence[Path],
    *,
    shards: int,
    cache_root: Path,
    compression_mode: str,
    backend: str,
) -> DistributedEncodingPlan:
    if shards < 1:
        raise ValueError("Number of shards must be >= 1")
    ordered_sources = sorted(path.resolve() for path in sources)
    groups: List[List[Path]] = [[] for _ in range(shards)]
    for index, path in enumerate(ordered_sources):
        groups[index % shards].append(path)
    descriptors = [
        ShardDescriptor(index=i, total=shards, sources=group) for i, group in enumerate(groups)
    ]
    return DistributedEncodingPlan(
        shards=descriptors,
        compression_mode=compression_mode,
        backend=backend,
        cache_root=cache_root,
    )


def write_plan_manifests(plan: DistributedEncodingPlan, root: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = plan.to_dict(root)
    (output_dir / "plan.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for shard in plan.shards:
        manifest = {
            "index": shard.index,
            "total": shard.total,
            "sources": [str(path.resolve().relative_to(root)) for path in shard.sources],
        }
        (output_dir / f"shard_{shard.index}.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )


def load_shard_manifest(root: Path, manifest_path: Path) -> ShardDescriptor:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    index = int(data["index"])
    total = int(data["total"])
    sources = [root / entry for entry in data.get("sources", [])]
    return ShardDescriptor(index=index, total=total, sources=sources)


def estimate_cluster_throughput(
    durations: Sequence[float],
    shard_duration: float,
) -> Dict[str, float]:
    if not durations:
        return {"speedup": 0.0, "efficiency": 0.0}
    sequential_time = sum(durations)
    if shard_duration <= 0.0:
        return {"speedup": float("inf"), "efficiency": 1.0}
    speedup = sequential_time / shard_duration
    efficiency = speedup / max(1, len(durations))
    return {"speedup": speedup, "efficiency": efficiency}


__all__ = [
    "DistributedEncodingPlan",
    "ShardDescriptor",
    "build_distributed_plan",
    "estimate_cluster_throughput",
    "load_shard_manifest",
    "write_plan_manifests",
]

