"""Run the public Quenyan benchmark suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, List, Optional, Set

from qyn1.benchmarks import (
    UnsupportedLanguageError,
    benchmark_dataset,
    load_manifest,
    summarise_to_json,
)


def _filter_descriptors(
    descriptors: Iterable, *, datasets: Optional[Set[str]], languages: Optional[Set[str]], categories: Optional[Set[str]]
):
    for descriptor in descriptors:
        if datasets and descriptor.slug not in datasets:
            continue
        if languages and descriptor.language.lower() not in {item.lower() for item in languages}:
            continue
        if categories and descriptor.category.lower() not in {item.lower() for item in categories}:
            continue
        yield descriptor


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Quenyan benchmark suite")
    parser.add_argument("workspace", type=Path, help="Directory used to cache downloads and extracted datasets")
    parser.add_argument("output", type=Path, help="Directory where encoded artefacts should be written")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/benchmark_suite_manifest.json"),
        help="Path to the benchmark manifest",
    )
    parser.add_argument(
        "--datasets",
        nargs="*",
        default=None,
        help="Specific dataset slugs to benchmark",
    )
    parser.add_argument(
        "--languages",
        nargs="*",
        default=None,
        help="Restrict benchmarks to the given languages",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Restrict benchmarks to the given size categories",
    )
    parser.add_argument(
        "--passphrase",
        default="benchmark-passphrase",
        help="Passphrase used for package encryption",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("benchmark_results.json"),
        help="Where to store the resulting metrics JSON",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if a dataset uses an unsupported language",
    )
    args = parser.parse_args(argv)

    manifest_data = json.loads(args.manifest.read_text())
    descriptors = load_manifest(args.manifest)
    selected = list(
        _filter_descriptors(
            descriptors,
            datasets=set(args.datasets) if args.datasets else None,
            languages=set(args.languages) if args.languages else None,
            categories=set(args.categories) if args.categories else None,
        )
    )

    args.workspace.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)

    results = []
    skipped = []
    for descriptor in selected:
        try:
            summary = benchmark_dataset(
                descriptor,
                workspace=args.workspace,
                output_dir=args.output,
                passphrase=args.passphrase,
            )
        except UnsupportedLanguageError as exc:
            if args.strict:
                raise
            skipped.append({"slug": descriptor.slug, "language": descriptor.language, "reason": str(exc)})
            continue
        results.append(summary)

    payload = {
        "manifest_version": manifest_data.get("version", "unknown"),
        "results": summarise_to_json(results),
        "skipped": skipped,
    }
    args.results.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
