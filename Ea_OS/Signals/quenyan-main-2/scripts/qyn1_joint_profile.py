"""Profile joint source statistics across compression presets using the benchmark corpus.

This driver walks the Quenyan 52-project benchmark corpus and, for each source
file, emits:
- QYN-1 packages encoded under the Balanced, Maximum, and Security presets.
- A sidecar ``.events.jsonl`` capturing the (T,P) token/payload events.
- A JSON summary with source size, token count, and compressed sizes.

Usage
-----
python scripts/qyn1_joint_profile.py <workspace> <output_dir> [--manifest ...]
                                     [--datasets ...] [--results ...]
                                     [--passphrase ...]
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

from qyn1.benchmarks import DatasetDescriptor, load_manifest, resolve_dataset
from qyn1.compression_config import CompressionConfig, get_compression_config
from qyn1.encoder import EncodedStream, QYNEncoder
from qyn1.event_logging import EncodingEventLog
from qyn1.language_detection import detect_language
from qyn1.package import encode_package
from qyn1.string_table import StringTable
from qyn1.token_optimisation import TokenOptimisationPlan, build_frequency_plan

logger = logging.getLogger("qyn1_joint_profile")


@dataclass
class FileProfile:
    """Metrics captured for a single source file."""

    path: Path
    size_bytes: int
    token_count: int
    compressed_bytes: Mapping[str, int]

    def to_dict(self, root: Path) -> Dict[str, object]:
        return {
            "path": str(self.path.relative_to(root)),
            "size_bytes": self.size_bytes,
            "token_count": self.token_count,
            "compressed_bytes": dict(self.compressed_bytes),
        }


@dataclass
class DatasetProfile:
    """Collection of per-file metrics for a dataset."""

    descriptor: DatasetDescriptor
    dataset_root: Path
    files: List[FileProfile]

    def to_dict(self) -> Dict[str, object]:
        return {
            "dataset": self.descriptor.slug,
            "language": self.descriptor.language,
            "category": self.descriptor.category,
            "file_count": len(self.files),
            "files": [entry.to_dict(self.dataset_root) for entry in self.files],
        }


def _discover_sources(root: Path, patterns: Iterable[str]) -> List[Path]:
    sources: List[Path] = []
    for pattern in patterns:
        sources.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted({path.resolve() for path in sources})


@dataclass
class _EncodedArtefact:
    stream: EncodedStream
    event_log: EncodingEventLog


@dataclass
class _ModeAssets:
    string_table: StringTable | None
    token_plan: TokenOptimisationPlan | None


def _encode_with_events(path: Path, encoder: QYNEncoder, *, language_hint: Optional[str]) -> _EncodedArtefact:
    raw = path.read_bytes()
    detection = detect_language(path, raw, language_hint=language_hint, default=encoder.language_profile_name)
    profile = detection.profile
    text, encoding = profile.decode_source(raw)
    event_log = EncodingEventLog(file_id=str(path))
    stream = encoder.encode(text, language_profile=profile, source_encoding=encoding, event_log=event_log)
    event_log.finalize()
    return _EncodedArtefact(stream=stream, event_log=event_log)


def _build_mode_assets(streams: Iterable[EncodedStream], config: CompressionConfig) -> _ModeAssets:
    if not config.wants_project_planning():
        return _ModeAssets(string_table=None, token_plan=None)
    payloads = []
    tokens: List[int] = []
    for stream in streams:
        payloads.extend(stream.payloads)
        if config.token_optimisation == "project":
            tokens.extend(stream.tokens)
    string_table = None
    if config.shared_string_table:
        string_table = StringTable.build_from_payloads(payloads)
    token_plan = None
    if config.token_optimisation == "project":
        token_plan = build_frequency_plan(tokens)
    return _ModeAssets(string_table=string_table, token_plan=token_plan)


def _write_events(path: Path, event_log: EncodingEventLog) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in event_log.events:
            handle.write(json.dumps(event.as_dict()))
            handle.write("\n")


def _encode_packages_for_file(
    stream: EncodedStream,
    event_log: EncodingEventLog,
    *,
    output_root: Path,
    relative_path: Path,
    configs: Mapping[str, CompressionConfig],
    mode_assets: Mapping[str, _ModeAssets],
    passphrase: str,
) -> Dict[str, int]:
    compressed_sizes: Dict[str, int] = {}
    string_table_for_events: StringTable | None = None
    for mode_name, config in configs.items():
        assets = mode_assets[mode_name]
        package = encode_package(
            stream,
            compression=config,
            string_table=assets.string_table,
            token_plan=assets.token_plan,
        )
        output_path = output_root / mode_name / relative_path.with_suffix(".qyn1")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        package_bytes = package.to_bytes(passphrase)
        output_path.write_bytes(package_bytes)
        compressed_sizes[mode_name] = len(package_bytes)
        if string_table_for_events is None:
            string_table_for_events = StringTable.from_bytes(package.string_table_bytes)
    if string_table_for_events is not None:
        event_log.attach_string_table(string_table_for_events)
    return compressed_sizes


def profile_dataset(
    descriptor: DatasetDescriptor,
    *,
    workspace: Path,
    output_root: Path,
    configs: Mapping[str, CompressionConfig],
    passphrase: str,
) -> DatasetProfile:
    logger.info("Profiling dataset %s", descriptor.slug)
    dataset_root = resolve_dataset(descriptor, workspace)
    sources = _discover_sources(dataset_root, descriptor.entry_glob)
    encoder = QYNEncoder()
    artefacts: Dict[Path, _EncodedArtefact] = {}
    for source_path in sources:
        artefacts[source_path] = _encode_with_events(source_path, encoder, language_hint=descriptor.language)
    mode_assets = {
        mode: _build_mode_assets((item.stream for item in artefacts.values()), config)
        for mode, config in configs.items()
    }
    file_profiles: List[FileProfile] = []
    for source_path, artefact in artefacts.items():
        relative_path = source_path.relative_to(dataset_root)
        compressed_sizes = _encode_packages_for_file(
            artefact.stream,
            artefact.event_log,
            output_root=output_root / descriptor.slug,
            relative_path=relative_path,
            configs=configs,
            mode_assets=mode_assets,
            passphrase=passphrase,
        )
        events_path = output_root / descriptor.slug / "events" / relative_path.with_suffix(".events.jsonl")
        _write_events(events_path, artefact.event_log)
        profile = FileProfile(
            path=source_path,
            size_bytes=source_path.stat().st_size,
            token_count=len(artefact.stream.tokens),
            compressed_bytes=compressed_sizes,
        )
        file_profiles.append(profile)
    return DatasetProfile(descriptor=descriptor, dataset_root=dataset_root, files=file_profiles)


def _load_descriptors(manifest_path: Path, *, datasets: Optional[List[str]]) -> List[DatasetDescriptor]:
    descriptors = load_manifest(manifest_path)
    if not datasets:
        return descriptors
    requested = {item.lower() for item in datasets}
    return [entry for entry in descriptors if entry.slug.lower() in requested]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Profile the joint source across compression presets")
    parser.add_argument("workspace", type=Path, help="Cache directory for dataset downloads and extractions")
    parser.add_argument("output", type=Path, help="Directory where packages and event logs will be written")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/benchmark_suite_manifest.json"),
        help="Path to the benchmark manifest",
    )
    parser.add_argument("--datasets", nargs="*", default=None, help="Restrict processing to specific dataset slugs")
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("joint_profile_results.json"),
        help="Where to write the aggregated summary JSON",
    )
    parser.add_argument("--passphrase", default="joint-profile", help="Passphrase used to encrypt packages")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    configs = {
        "balanced": get_compression_config("balanced"),
        "maximum": get_compression_config("maximum"),
        "security": get_compression_config("security"),
    }

    descriptors = _load_descriptors(args.manifest, datasets=args.datasets)
    if not descriptors:
        logger.warning("No datasets matched the provided filters; exiting")
        return 0

    args.workspace.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)

    dataset_profiles = [
        profile_dataset(
            descriptor,
            workspace=args.workspace,
            output_root=args.output,
            configs=configs,
            passphrase=args.passphrase,
        )
        for descriptor in descriptors
    ]

    manifest_data = json.loads(args.manifest.read_text())
    payload = {
        "manifest_version": manifest_data.get("version", "unknown"),
        "datasets": [profile.to_dict() for profile in dataset_profiles],
    }
    args.results.write_text(json.dumps(payload, indent=2))
    logger.info("Wrote summary to %s", args.results)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
