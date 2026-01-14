"""Offline statistical analysis of token/payload event logs.

This script consumes the `.events.jsonl` files emitted by `scripts/qyn1_joint_profile.py`
(or any other pipeline that exports ``EncodingEvent`` rows) and produces aggregate
histograms, entropy calculations, and coarse bit-allocation estimates. The analysis
operates purely on disk artefacts—event logs and encrypted MCS containers—so it can
run offline against previously captured datasets.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Tuple

from qyn1.benchmarks import DatasetDescriptor, load_manifest
from qyn1.crypto import EncryptionResult, decrypt
from qyn1.event_logging import EventPayloadClass
from qyn1.format import PAYLOAD_MAGIC, FrameFormatError, decode_sections, read_frame
from qyn1.measurement import conditional_entropy, entropy
from qyn1.package import PackageMetadata, WRAPPER_MAGIC

logger = logging.getLogger("event_statistics")


@dataclass(frozen=True)
class PayloadSignature:
    """JSON-serialisable representation of a payload observation."""

    payload_class: EventPayloadClass
    value_repr: str | None
    domain: str | None

    @classmethod
    def from_event(cls, payload_class: str, payload_value: object, payload_domain: object) -> "PayloadSignature":
        normalised_class = EventPayloadClass(payload_class)
        if payload_value is None:
            value_repr: str | None = None
        elif isinstance(payload_value, (str, int, float, bool)):
            value_repr = str(payload_value)
        else:
            value_repr = json.dumps(payload_value, sort_keys=True)
        domain_value = str(payload_domain) if payload_domain is not None else None
        return cls(payload_class=normalised_class, value_repr=value_repr, domain=domain_value)

    def serialise(self) -> str:
        return json.dumps({
            "class": self.payload_class.value,
            "value": self.value_repr,
            "domain": self.domain,
        }, sort_keys=True)


@dataclass
class StatisticalSnapshot:
    """Collection of counters and derived measurements for a slice of data."""

    token_counter: Counter[str] = field(default_factory=Counter)
    payload_class_counter: Counter[str] = field(default_factory=Counter)
    joint_counter: Counter[Tuple[str, str]] = field(default_factory=Counter)
    per_class_joint: Dict[str, Counter[Tuple[str, str]]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    token_count: int = 0
    string_payload_token_count: int = 0
    payload_event_counter: Counter[str] = field(default_factory=Counter)
    bits_tokens: int = 0
    bits_strings: int = 0
    package_bytes: int = 0
    source_bytes: int = 0

    def merge(self, other: "StatisticalSnapshot") -> None:
        self.token_counter.update(other.token_counter)
        self.payload_class_counter.update(other.payload_class_counter)
        self.joint_counter.update(other.joint_counter)
        for payload_class, counter in other.per_class_joint.items():
            self.per_class_joint[payload_class].update(counter)
        self.token_count += other.token_count
        self.string_payload_token_count += other.string_payload_token_count
        self.payload_event_counter.update(other.payload_event_counter)
        self.bits_tokens += other.bits_tokens
        self.bits_strings += other.bits_strings
        self.package_bytes += other.package_bytes
        self.source_bytes += other.source_bytes

    @property
    def _conditional_entropy(self) -> float:
        return conditional_entropy(self.joint_counter)

    def entropy_report(self) -> Dict[str, float]:
        joint_entropy = entropy(self.joint_counter)
        token_entropy = entropy(self.token_counter)
        return {
            "H_T": token_entropy,
            "H_P_given_T": self._conditional_entropy,
            "H_joint": joint_entropy,
            "H_by_payload_class": {
                cls: conditional_entropy(counter)
                for cls, counter in self.per_class_joint.items()
            },
        }

    def histogram_report(self) -> Dict[str, object]:
        token_total = max(self.token_count, 1)
        payload_totals: Counter[str] = Counter()
        for (token, _), count in self.joint_counter.items():
            payload_totals[token] += count
        conditional_probabilities: Dict[str, Dict[str, float]] = defaultdict(dict)
        for (token, payload_serialised), count in self.joint_counter.items():
            conditional_probabilities[token][payload_serialised] = count / payload_totals[token]
        return {
            "token_histogram": dict(self.token_counter),
            "token_probabilities": {
                token: count / token_total for token, count in self.token_counter.items()
            },
            "payload_class_histogram": dict(self.payload_class_counter),
            "payload_given_token": conditional_probabilities,
        }

    def bit_allocation_report(self) -> Dict[str, object]:
        if self.token_count == 0:
            return {
                "bits_per_token": 0.0,
                "bits_per_payload_token": 0.0,
                "combined_bits_per_token": 0.0,
                "bits_per_payload_event": {},
                "tokens_with_string_payload": 0,
                "bits_per_source_byte": 0.0,
                "bytes_per_source_byte": 0.0,
            }
        bits_per_token = self.bits_tokens / self.token_count
        bits_per_payload_token = (
            self.bits_strings / self.string_payload_token_count
            if self.string_payload_token_count
            else 0.0
        )
        string_payload_events = (
            self.payload_event_counter.get(EventPayloadClass.ID.value, 0)
            + self.payload_event_counter.get(EventPayloadClass.STR.value, 0)
        )
        other_events = sum(self.payload_event_counter.values()) - string_payload_events
        bits_per_payload_event: Dict[str, float] = {}
        if string_payload_events:
            per_event = self.bits_strings / string_payload_events
            bits_per_payload_event[EventPayloadClass.ID.value] = per_event
            bits_per_payload_event[EventPayloadClass.STR.value] = per_event
        if other_events:
            per_event_other = self.bits_tokens / other_events
            for payload_class in EventPayloadClass:
                if payload_class in (EventPayloadClass.ID, EventPayloadClass.STR):
                    continue
                bits_per_payload_event[payload_class.value] = per_event_other
        total_bits = self.bits_tokens + self.bits_strings
        bits_per_source_byte = (
            total_bits / max(self.source_bytes, 1)
            if self.source_bytes
            else 0.0
        )
        bytes_per_source_byte = (
            self.package_bytes / max(self.source_bytes, 1)
            if self.source_bytes
            else 0.0
        )
        return {
            "bits_per_token": bits_per_token,
            "bits_per_payload_token": bits_per_payload_token,
            "combined_bits_per_token": total_bits / self.token_count,
            "bits_per_payload_event": bits_per_payload_event,
            "tokens_with_string_payload": self.string_payload_token_count,
            "package_bytes": self.package_bytes,
            "source_bytes": self.source_bytes,
            "bits_per_source_byte": bits_per_source_byte,
            "bytes_per_source_byte": bytes_per_source_byte,
        }

    def to_report(self) -> Dict[str, object]:
        return {
            "token_count": self.token_count,
            "string_payload_token_count": self.string_payload_token_count,
            "histograms": self.histogram_report(),
            "entropy": self.entropy_report(),
            "bits": self.bit_allocation_report(),
        }


@dataclass(frozen=True)
class EventLogContext:
    dataset: DatasetDescriptor
    relative_path: Path
    event_path: Path
    package_path: Path
    source_bytes: int
    compressed_bytes: int


@dataclass(frozen=True)
class _FileSizeProfile:
    source_bytes: int
    compressed_bytes: Dict[str, int]


def _load_file_size_profiles(path: Optional[Path]) -> Dict[Tuple[str, str], _FileSizeProfile]:
    if path is None:
        return {}
    if not path.exists():
        logger.warning("Profile results %s not found; size-based metrics will be empty", path)
        return {}
    raw = json.loads(path.read_text())
    profiles: Dict[Tuple[str, str], _FileSizeProfile] = {}
    for dataset in raw.get("datasets", []):
        slug = dataset.get("dataset")
        for entry in dataset.get("files", []):
            relative_path = entry.get("path")
            source_bytes = int(entry.get("size_bytes", 0) or 0)
            compressed_bytes = entry.get("compressed_bytes", {}) or {}
            if slug is None or relative_path is None:
                continue
            profiles[(slug, str(relative_path))] = _FileSizeProfile(
                source_bytes=source_bytes, compressed_bytes=compressed_bytes
            )
    return profiles


def _iter_event_rows(path: Path) -> Iterator[Mapping[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise ValueError(f"Failed to parse {path} line {line_number}") from exc


def _parse_event_log(path: Path) -> StatisticalSnapshot:
    positions: Dict[int, str] = {}
    snapshot = StatisticalSnapshot()
    payload_tokens_with_strings: set[int] = set()
    for row in _iter_event_rows(path):
        token_key = str(row["token_key"])
        position = int(row["position"])
        payload_class = str(row["payload_class"])
        payload_value = row.get("payload_value")
        payload_domain = row.get("payload_domain")

        signature = PayloadSignature.from_event(payload_class, payload_value, payload_domain)
        serialised_signature = signature.serialise()
        positions[position] = token_key

        snapshot.payload_class_counter[payload_class] += 1
        snapshot.joint_counter[(token_key, serialised_signature)] += 1
        snapshot.per_class_joint[payload_class][(token_key, serialised_signature)] += 1
        snapshot.payload_event_counter[payload_class] += 1
        if signature.payload_class in {EventPayloadClass.ID, EventPayloadClass.STR}:
            payload_tokens_with_strings.add(position)

    snapshot.token_counter.update(positions.values())
    snapshot.token_count = len(positions)
    snapshot.string_payload_token_count = len(payload_tokens_with_strings)
    return snapshot


def _strip_event_suffix(path: Path) -> Path:
    suffix = ".events.jsonl"
    if not path.name.endswith(suffix):
        return path
    stripped = path.name[: -len(suffix)]
    return path.with_name(stripped)


def _locate_package(event_path: Path, mode: str) -> Path:
    """Return the expected MCS package path for the provided event log."""

    events_root = event_path.parent.parent
    relative = _strip_event_suffix(event_path.relative_to(events_root))
    return (events_root.parent / mode / relative).with_suffix(".qyn1")


def _load_sections(package_bytes: bytes, passphrase: str) -> Dict[int, bytes]:
    wrapper_frame, _ = read_frame(package_bytes, expected_magic=WRAPPER_MAGIC)
    wrapper_data = json.loads(wrapper_frame.body.decode("utf-8"))
    metadata = PackageMetadata.from_dict(wrapper_data.get("metadata", {}))
    encrypted = EncryptionResult(
        nonce=base64.b64decode(wrapper_data["nonce"]),
        salt=base64.b64decode(wrapper_data["salt"]),
        hkdf_salt=base64.b64decode(wrapper_data.get("hkdf_salt", wrapper_data["salt"])),
        ciphertext=base64.b64decode(wrapper_data["ciphertext"]),
        tag=base64.b64decode(wrapper_data["tag"]),
        version=int(wrapper_data.get("encryption_version", 1)),
        aead=str(wrapper_data.get("aead", "chacha20poly1305")),
        kdf=str(wrapper_data.get("kdf", "pbkdf2")),
        kdf_parameters={
            key: int(value) for key, value in dict(wrapper_data.get("kdf_parameters", {})).items()
        },
    )
    payload_envelope = decrypt(encrypted, passphrase, metadata.to_associated_data())
    payload_frame, _ = read_frame(payload_envelope, expected_magic=PAYLOAD_MAGIC)
    sections: Dict[int, bytes] = {}
    for section in decode_sections(payload_frame.body):
        sections[section.identifier] = section.payload
    return sections


def _attach_bit_estimates(snapshot: StatisticalSnapshot, package_path: Path, passphrase: str) -> None:
    try:
        sections = _load_sections(package_path.read_bytes(), passphrase)
    except (FileNotFoundError, FrameFormatError, ValueError, KeyError) as exc:
        logger.warning("Skipping bit accounting for %s: %s", package_path, exc)
        return
    snapshot.bits_tokens = len(sections.get(0x0003, b"")) * 8
    snapshot.bits_strings = len(sections.get(0x0004, b"")) * 8
    snapshot.package_bytes = package_path.stat().st_size


def _build_contexts(
    events_root: Path,
    manifest: Mapping[str, DatasetDescriptor],
    mode: str,
    file_sizes: Mapping[Tuple[str, str], _FileSizeProfile] | None,
) -> Iterator[EventLogContext]:
    for event_path in events_root.rglob("*.events.jsonl"):
        relative = event_path.relative_to(events_root)
        slug = relative.parts[0]
        dataset = manifest.get(slug)
        if dataset is None:
            logger.warning("Ignoring events for unknown dataset %s", slug)
            continue
        try:
            relative_path = event_path.relative_to(events_root / slug / "events")
        except ValueError:
            logger.warning("Events path %s does not follow expected layout", event_path)
            continue
        package_path = _locate_package(event_path, mode)
        key = (slug, str(_strip_event_suffix(relative_path)))
        profile = file_sizes.get(key) if file_sizes else None
        yield EventLogContext(
            dataset=dataset,
            relative_path=_strip_event_suffix(relative_path),
            event_path=event_path,
            package_path=package_path,
            source_bytes=profile.source_bytes if profile else 0,
            compressed_bytes=(profile.compressed_bytes.get(mode, 0) if profile else 0),
        )


def _aggregate_by_key(contexts: Iterable[EventLogContext], key_func) -> Dict[str, List[EventLogContext]]:
    buckets: Dict[str, List[EventLogContext]] = defaultdict(list)
    for context in contexts:
        buckets[key_func(context)].append(context)
    return buckets


def _analyse_context(context: EventLogContext, passphrase: str) -> StatisticalSnapshot:
    snapshot = _parse_event_log(context.event_path)
    _attach_bit_estimates(snapshot, context.package_path, passphrase)
    snapshot.source_bytes = context.source_bytes
    if snapshot.package_bytes == 0:
        snapshot.package_bytes = context.compressed_bytes
    return snapshot


def _extract_summary_block(report: Mapping[str, object]) -> Mapping[str, object]:
    summary = report.get("summary") if isinstance(report, Mapping) else None
    return summary if isinstance(summary, Mapping) else report


def _compare_entropy(current: Mapping[str, object], baseline: Mapping[str, object]) -> Dict[str, object]:
    cond_current = current.get("H_by_payload_class", {}) if isinstance(current, Mapping) else {}
    cond_baseline = baseline.get("H_by_payload_class", {}) if isinstance(baseline, Mapping) else {}
    conditional: Dict[str, Dict[str, object]] = {}
    for payload_class, baseline_value in cond_baseline.items():
        current_value = cond_current.get(payload_class, 0.0)
        conditional[payload_class] = {
            "delta": current_value - baseline_value,
            "improved": current_value <= baseline_value,
        }
    return {
        "token_entropy_delta": current.get("H_T", 0.0) - baseline.get("H_T", 0.0),
        "joint_entropy_delta": current.get("H_joint", 0.0) - baseline.get("H_joint", 0.0),
        "token_entropy_improved": current.get("H_T", 0.0) <= baseline.get("H_T", 0.0),
        "joint_entropy_improved": current.get("H_joint", 0.0) <= baseline.get("H_joint", 0.0),
        "conditional_entropy": conditional,
    }


def _compare_bits(current: Mapping[str, object], baseline: Mapping[str, object]) -> Dict[str, object]:
    keys = (
        "bits_per_token",
        "bits_per_payload_token",
        "combined_bits_per_token",
        "bits_per_source_byte",
        "bytes_per_source_byte",
    )
    deltas: Dict[str, float] = {}
    improvements: Dict[str, bool] = {}
    for key in keys:
        current_value = float(current.get(key, 0.0) or 0.0)
        baseline_value = float(baseline.get(key, 0.0) or 0.0)
        deltas[key] = current_value - baseline_value
        improvements[key] = current_value <= baseline_value
    return {
        "delta": deltas,
        "improved": improvements,
    }


def _compare_snapshot_reports(current: Mapping[str, object], baseline: Mapping[str, object]) -> Dict[str, object]:
    current_summary = _extract_summary_block(current)
    baseline_summary = _extract_summary_block(baseline)
    entropy_current = current_summary.get("entropy", {}) if isinstance(current_summary, Mapping) else {}
    entropy_baseline = baseline_summary.get("entropy", {}) if isinstance(baseline_summary, Mapping) else {}
    bits_current = current_summary.get("bits", {}) if isinstance(current_summary, Mapping) else {}
    bits_baseline = baseline_summary.get("bits", {}) if isinstance(baseline_summary, Mapping) else {}
    return {
        "entropy": _compare_entropy(entropy_current, entropy_baseline),
        "bits": _compare_bits(bits_current, bits_baseline),
    }


def compare_reports(current: Mapping[str, object], baseline: Mapping[str, object]) -> Dict[str, object]:
    comparison: Dict[str, object] = {}
    if "overall" in current and "overall" in baseline:
        comparison["overall"] = _compare_snapshot_reports(current["overall"], baseline["overall"])

    def _compare_groups(key: str) -> None:
        current_group = current.get(key, {}) if isinstance(current, Mapping) else {}
        baseline_group = baseline.get(key, {}) if isinstance(baseline, Mapping) else {}
        if not isinstance(current_group, Mapping) or not isinstance(baseline_group, Mapping):
            return
        intersection = current_group.keys() & baseline_group.keys()
        comparison[key] = {
            name: _compare_snapshot_reports(current_group[name], baseline_group[name])
            for name in intersection
        }

    _compare_groups("by_language")
    _compare_groups("by_project")
    _compare_groups("by_project_class")
    return comparison


def _summarise_group(
    name: str, contexts: List[EventLogContext], passphrase: str
) -> Tuple[Dict[str, object], StatisticalSnapshot]:
    summary = StatisticalSnapshot()
    per_file: Dict[str, Dict[str, object]] = {}
    for context in contexts:
        snapshot = _analyse_context(context, passphrase)
        summary.merge(snapshot)
        per_file[str(context.relative_path)] = snapshot.to_report()
    return (
        {
            "name": name,
            "summary": summary.to_report(),
            "files": per_file,
        },
        summary,
    )


def analyse(
    events_root: Path,
    manifest_path: Path,
    *,
    mode: str,
    passphrase: str,
    output: Path,
    profile_results: Optional[Path] = None,
    baseline_report: Optional[Path] = None,
) -> None:
    datasets = {item.slug: item for item in load_manifest(manifest_path)}
    file_sizes = _load_file_size_profiles(profile_results)
    contexts = list(_build_contexts(events_root, datasets, mode, file_sizes))
    language_groups = _aggregate_by_key(contexts, lambda ctx: ctx.dataset.language)
    domain_groups = _aggregate_by_key(contexts, lambda ctx: ctx.dataset.domain)
    project_groups = _aggregate_by_key(contexts, lambda ctx: ctx.dataset.slug)

    overall = StatisticalSnapshot()
    project_reports: Dict[str, object] = {}
    language_reports: Dict[str, object] = {}
    domain_reports: Dict[str, object] = {}

    for slug, group in project_groups.items():
        report, snapshot = _summarise_group(slug, group, passphrase)
        project_reports[slug] = {
            "dataset": {
                "slug": group[0].dataset.slug,
                "language": group[0].dataset.language,
                "category": group[0].dataset.category,
                "domain": group[0].dataset.domain,
            },
            **report,
        }
        overall.merge(snapshot)

    for language, group in language_groups.items():
        language_reports[language], _ = _summarise_group(
            language, group, passphrase
        )

    for domain, group in domain_groups.items():
        domain_reports[domain], _ = _summarise_group(domain, group, passphrase)

    output.parent.mkdir(parents=True, exist_ok=True)
    baseline_payload: Mapping[str, object] = {}
    if baseline_report is not None:
        if baseline_report.exists():
            baseline_payload = json.loads(baseline_report.read_text())
        else:
            logger.warning("Baseline report %s not found; skipping comparison", baseline_report)

    output.write_text(
        json.dumps(
            {
                "overall": overall.to_report(),
                "by_project": project_reports,
                "by_language": language_reports,
                "by_project_class": domain_reports,
                "baseline_comparison": compare_reports(
                    {
                        "overall": overall.to_report(),
                        "by_project": project_reports,
                        "by_language": language_reports,
                        "by_project_class": domain_reports,
                    },
                    baseline_payload,
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_root", type=Path, help="Root directory containing <dataset>/events trees")
    parser.add_argument("--manifest", type=Path, default=Path("data/benchmark_suite_manifest.json"))
    parser.add_argument("--mode", default="balanced", help="Compression mode subdirectory to read packages from")
    parser.add_argument("--passphrase", default="joint-profile", help="Passphrase used to decrypt MCS containers")
    parser.add_argument("--output", type=Path, default=Path("data/event_statistics.json"), help="Destination for the analysis report")
    parser.add_argument(
        "--profile-results",
        type=Path,
        default=None,
        help="Optional joint_profile_results.json to derive source/compressed byte ratios",
    )
    parser.add_argument(
        "--baseline-report",
        type=Path,
        default=None,
        help="Existing statistics JSON to compare against for refinement validation",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    analyse(
        args.events_root,
        args.manifest,
        mode=args.mode,
        passphrase=args.passphrase,
        output=args.output,
        profile_results=args.profile_results,
        baseline_report=args.baseline_report,
    )


if __name__ == "__main__":
    main()
