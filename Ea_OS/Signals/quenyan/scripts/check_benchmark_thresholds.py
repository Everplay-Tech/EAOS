"""Validate benchmark output against CI guard rails.

The script consumes ``benchmark_output.json`` produced by the Criterion
bridging layer in the Rust reference implementation.  It asserts that throughput,
archive size, and decode latency stay within acceptable tolerances so that
regressions are surfaced early in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "benchmark_output.json"

THROUGHPUT_MIN = 20.0
ARCHIVE_MAX = 2048
DECODE_MAX_US = 500.0


def main() -> None:
    if not REPORT.exists():
        raise SystemExit(f"benchmark report missing: {REPORT}")
    data = json.loads(REPORT.read_text("utf-8"))
    sample_loc = max(1, int(data.get("sample_loc", 1)))
    failures = []
    for entry in data.get("results", []):
        name = entry.get("name", "unknown")
        encode_time = float(entry.get("encode_time_us", 0.0))
        decode_time = float(entry.get("decode_time_us", 0.0))
        size_bytes = int(entry.get("size_bytes", 0))
        throughput = sample_loc / encode_time if encode_time else 0.0
        if throughput < THROUGHPUT_MIN:
            failures.append(
                f"{name}: throughput {throughput:.2f} < minimum {THROUGHPUT_MIN}"
            )
        if size_bytes > ARCHIVE_MAX:
            failures.append(
                f"{name}: archive size {size_bytes} > maximum {ARCHIVE_MAX}"
            )
        if decode_time > DECODE_MAX_US:
            failures.append(
                f"{name}: decode time {decode_time:.2f} > maximum {DECODE_MAX_US}"
            )
    if failures:
        details = "\n".join(failures)
        raise SystemExit(f"Benchmark thresholds failed:\n{details}")


if __name__ == "__main__":
    main()
