"""Analyse compression ratios for the pre-recorded comparison dataset."""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "compression_ratio_comparison.json"


def _ratio(value: int, baseline: int) -> float:
    if baseline == 0:
        return 0.0
    return value / baseline


def analyse_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    sizes = entry["sizes"]
    baseline = sizes["source_bytes"]
    result = {
        "name": entry["name"],
        "language": entry["language"],
        "category": entry["category"],
        "ratios": {
            "gzip": _ratio(sizes["gzip_bytes"], baseline),
            "brotli": _ratio(sizes["brotli_bytes"], baseline),
            "binary_ast": _ratio(sizes["binary_ast_bytes"], baseline),
            "mcs_balanced": _ratio(sizes["mcs_balanced_bytes"], baseline),
            "mcs_maximum": _ratio(sizes["mcs_maximum_bytes"], baseline),
            "mcs_security": _ratio(sizes["mcs_security_bytes"], baseline),
        },
    }
    if "minified_gzip_bytes" in sizes:
        result["ratios"]["minified_gzip"] = _ratio(
            sizes["minified_gzip_bytes"], baseline
        )
    return result


def summarise(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    buckets: Dict[str, List[float]] = {}
    for entry in results:
        for key, value in entry["ratios"].items():
            buckets.setdefault(key, []).append(value)
    summary = {}
    for key, values in buckets.items():
        summary[key] = {
            "mean_ratio": statistics.mean(values),
            "median_ratio": statistics.median(values),
            "stdev": statistics.pstdev(values),
        }
    return summary


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    entries = [analyse_entry(entry) for entry in data["projects"]]
    report = {
        "generated_at": data.get("generated_at"),
        "project_count": data.get("project_count", len(entries)),
        "entries": entries,
        "summary": summarise(entries),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
