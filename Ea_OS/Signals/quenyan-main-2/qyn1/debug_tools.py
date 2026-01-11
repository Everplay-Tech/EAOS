"""Developer tooling for inspecting and validating QYN-1 packages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import qyn1.package as package_module

from .encoder import EncodedStream
from .package import (
    _canonicalise_json,
    _extract_wrapper_components,
    decode_package,
)
from .format import FrameFormatError, read_frame
from .package import decode_package


@dataclass
class InspectionReport:
    """High level package metadata available without decrypting payload."""

    version: str
    size_bytes: int
    metadata: Dict[str, Any]
    signature_valid: Optional[bool]
    provenance: Optional[Dict[str, Any]]
    audit_issues: Optional[List[str]]

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "version": self.version,
            "size_bytes": self.size_bytes,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        if self.signature_valid is not None:
            payload["signature_valid"] = self.signature_valid
        if self.provenance is not None:
            payload["provenance"] = self.provenance
        if self.audit_issues is not None:
            payload["audit_issues"] = self.audit_issues
        return payload


def inspect_wrapper(path: Path, validate_audit: bool = False) -> InspectionReport:
    """Inspect wrapper metadata without decrypting payload."""

    data = path.read_bytes()
    structured, version_obj, wrapper, _ = _extract_wrapper_components(data)
    version = wrapper.get("version", version_obj.text if structured else "unknown")
    raw_metadata = wrapper.get("metadata", {})
    metadata: Dict[str, Any]
    signature_valid: Optional[bool] = None
    provenance: Optional[Dict[str, Any]] = None
    audit_issues: Optional[List[str]] = None
    if isinstance(raw_metadata, dict):
        metadata = raw_metadata
        integrity = metadata.get("integrity_signature")
        provenance_val = metadata.get("provenance")
        if isinstance(provenance_val, dict):
            provenance = provenance_val
        if isinstance(integrity, dict):
            signature_valid = _verify_integrity_signature(metadata, integrity)
        if validate_audit:
            audit_trail = metadata.get("audit_trail")
            if isinstance(audit_trail, list):
                audit_issues = _validate_audit_trail(audit_trail)
    else:
        metadata = {"error": "metadata missing"}
    return InspectionReport(
        version=str(version),
        size_bytes=path.stat().st_size,
        metadata=metadata,
        signature_valid=signature_valid,
        provenance=provenance,
        audit_issues=audit_issues,
    )
    if not data.startswith(package_module.WRAPPER_MAGIC):
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        version = str(wrapper.get("version", "unknown"))
    else:
        try:
            frame, remainder = read_frame(data, expected_magic=package_module.WRAPPER_MAGIC)
        except FrameFormatError as exc:  # pragma: no cover - sanity guard
            raise ValueError("failed to parse package wrapper") from exc
        if remainder:
            raise ValueError("unexpected trailing data after wrapper frame")
        wrapper = json.loads(frame.body.decode("utf-8"))
        version = str(wrapper.get("version", frame.version.text))
    metadata = wrapper.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {"error": "metadata missing"}
    return InspectionReport(version=version, size_bytes=path.stat().st_size, metadata=metadata)


def decode_for_debug(path: Path, passphrase: str) -> EncodedStream:
    return decode_package(path.read_bytes(), passphrase)


def _verify_integrity_signature(metadata: Dict[str, Any], integrity: Dict[str, Any]) -> bool:
    algorithm = str(integrity.get("algorithm", "sha256")).lower()
    value = str(integrity.get("value", ""))
    if not value:
        return False
    canonical_source = {k: v for k, v in metadata.items() if k != "integrity_signature"}
    canonical_json = _canonicalise_json(canonical_source)
    try:
        hasher = hashlib.new(algorithm)
    except ValueError:
        return False
    hasher.update(canonical_json.encode("utf-8"))
    return hasher.hexdigest() == value.lower()


def _validate_audit_trail(audit_trail: List[Dict[str, Any]]) -> List[str]:
    issues: List[str] = []
    previous: Optional[datetime] = None
    for index, entry in enumerate(audit_trail):
        timestamp = entry.get("timestamp")
        if timestamp is None:
            issues.append(f"entry {index} missing timestamp")
            continue
        try:
            current = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            issues.append(f"entry {index} has invalid timestamp '{timestamp}'")
            continue
        if previous and current < previous:
            issues.append(f"entry {index} occurs before entry {index - 1}")
        previous = current
        if not entry.get("action"):
            issues.append(f"entry {index} missing action field")
    return issues


def diff_streams(a: EncodedStream, b: EncodedStream) -> Dict[str, object]:
    """Compute a semantic diff between two morphemic streams."""

    token_deltas: List[Tuple[int, str, str]] = []
    for index, (token_a, token_b) in enumerate(zip(a.tokens, b.tokens)):
        if token_a == token_b:
            continue
        entry_a = a.dictionary.entry_for_index(token_a)
        entry_b = b.dictionary.entry_for_index(token_b)
        token_deltas.append((index, entry_a.key, entry_b.key))
    length_delta = len(a.tokens) - len(b.tokens)
    payload_delta = len(a.payloads) - len(b.payloads)
    return {
        "token_differences": token_deltas,
        "length_delta": length_delta,
        "payload_delta": payload_delta,
    }


def lint_stream(stream: EncodedStream) -> List[str]:
    """Run lightweight static analysis on the morpheme stream."""

    issues: List[str] = []
    for index, token in enumerate(stream.tokens):
        entry = stream.dictionary.entry_for_index(token)
        if entry.key.startswith("meta:unknown"):
            issues.append(f"token {index} maps to unknown entry '{entry.key}'")
    if stream.source_map is None:
        issues.append("package is missing a source map")
    else:
        if len(stream.source_map.entries) != len(stream.tokens):
            issues.append("source map entry count does not match token count")
    return issues


def summarise_source_map(stream: EncodedStream) -> Dict[str, object]:
    if stream.source_map is None:
        return {"available": False}
    summary = stream.source_map.summary()
    summary["available"] = True
    return summary
