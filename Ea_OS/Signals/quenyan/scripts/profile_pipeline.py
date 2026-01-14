"""Profile the encoding pipeline to identify bottlenecks."""

from __future__ import annotations

import argparse
import cProfile
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qyn1.encoder import QYNEncoder
from qyn1.package import encode_package


def run_workload() -> None:
    source = """
def compute(values: list[int]) -> int:
    total = 0
    for value in values:
        if value % 2 == 0:
            total += value * 2
        else:
            total += value
    return total
"""
    encoder = QYNEncoder()
    stream = encoder.encode(source)
    package = encode_package(stream, backend_name="chunked-rans")
    package.to_bytes("profile-passphrase")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/pipeline_profile.json"))
    args = parser.parse_args()

    profiler = cProfile.Profile()
    profiler.enable()
    run_workload()
    profiler.disable()

    stats = profiler.getstats()
    top = sorted(stats, key=lambda entry: entry.totaltime, reverse=True)[:15]
    summary = []
    for entry in top:
        code_obj = entry.code
        if hasattr(code_obj, "co_filename"):
            label = f"{code_obj.co_filename}:{code_obj.co_name}"
        else:
            label = str(code_obj)
        summary.append(
            {
                "function": label,
                "callcount": entry.callcount,
                "totaltime": entry.totaltime,
                "inlinetime": entry.inlinetime,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
