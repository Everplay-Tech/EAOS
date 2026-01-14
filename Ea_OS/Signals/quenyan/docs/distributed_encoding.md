# Distributed Encoding Architecture

Large monorepos can split encoding work across a compute cluster using the
`qyn1.distributed` helpers. The planner assigns sources to shards in a
round-robin fashion, generating JSON manifests (`plan.json` and
`shard_{index}.json`) that can be fed to CI jobs.

```python
from pathlib import Path
from qyn1.distributed import build_distributed_plan, write_plan_manifests

sources = [path for path in Path("src").rglob("*.py")]
plan = build_distributed_plan(
    sources,
    shards=8,
    cache_root=Path(".qyn-cache"),
    compression_mode="balanced",
    backend="rans",
)
write_plan_manifests(plan, Path.cwd(), Path("build/manifests"))
```

Each worker loads its shard manifest and invokes the incremental encoder with
matching `--shard-index`/`--shard-count`. The helper `estimate_cluster_throughput`
computes coarse-grained speedup/efficiency metrics from observed shard durations
and single-thread timings.
