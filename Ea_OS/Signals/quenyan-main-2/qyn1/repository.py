"""Repository-level storage format helpers for encoded projects."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional


def _relpath(path: Path, root: Path) -> Path:
    return path.resolve().relative_to(root.resolve())


@dataclass
class RepositoryEntry:
    """Metadata describing a single encoded source file."""

    source: Path
    package_hash: str
    size: int
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "source": str(self.source),
            "package_hash": self.package_hash,
            "size": self.size,
            "metadata": self.metadata,
        }


@dataclass
class RepositoryIndex:
    """Manifest describing a repository archive."""

    version: str
    entries: List[RepositoryEntry]
    compression_mode: str
    backend: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": self.version,
            "compression_mode": self.compression_mode,
            "backend": self.backend,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "RepositoryIndex":
        entries = [
            RepositoryEntry(
                source=Path(item["source"]),
                package_hash=str(item["package_hash"]),
                size=int(item["size"]),
                metadata=dict(item.get("metadata", {})),
            )
            for item in payload.get("entries", [])
        ]
        return cls(
            version=str(payload.get("version", "1.0")),
            entries=entries,
            compression_mode=str(payload.get("compression_mode", "balanced")),
            backend=str(payload.get("backend", "rans")),
        )


class RepositoryWriter:
    """Construct repository archives with content-addressed storage."""

    INDEX_VERSION = "1.0"

    def __init__(self, root: Path, destination: Path, *, compression_mode: str, backend: str) -> None:
        self._root = root.resolve()
        self._destination = destination
        self._objects_dir = destination / "objects"
        self._mirror_dir = destination / "mirror"
        self._compression_mode = compression_mode
        self._backend = backend
        self._entries: List[RepositoryEntry] = []

    def add_package(
        self,
        source: Path,
        package_bytes: bytes,
        *,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> None:
        relative = _relpath(source, self._root)
        digest = hashlib.sha256(package_bytes).hexdigest()
        object_path = self._objects_dir / digest[:2] / f"{digest[2:]}.qyn1"
        if not object_path.exists():
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.write_bytes(package_bytes)
        mirror_rel = relative.parent / f"{relative.name}.qyn1"
        mirror_path = self._mirror_dir / mirror_rel
        mirror_path.parent.mkdir(parents=True, exist_ok=True)
        mirror_path.write_bytes(package_bytes)
        entry = RepositoryEntry(
            source=relative,
            package_hash=digest,
            size=len(package_bytes),
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)

    def finalise(self) -> RepositoryIndex:
        index = RepositoryIndex(
            version=self.INDEX_VERSION,
            entries=sorted(self._entries, key=lambda item: str(item.source)),
            compression_mode=self._compression_mode,
            backend=self._backend,
        )
        self._destination.mkdir(parents=True, exist_ok=True)
        index_path = self._destination / "index.json"
        index_path.write_text(json.dumps(index.to_dict(), indent=2), encoding="utf-8")
        return index

    def build_monolithic_archive(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(self._mirror_dir.rglob("*.qyn1")):
                archive.write(file_path, file_path.relative_to(self._mirror_dir))


def load_repository_index(path: Path) -> RepositoryIndex:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RepositoryIndex.from_dict(payload)


def diff_repository_indexes(
    current: RepositoryIndex, previous: RepositoryIndex
) -> Dict[str, List[str]]:
    current_map = {entry.source: entry for entry in current.entries}
    previous_map = {entry.source: entry for entry in previous.entries}
    added = sorted(str(path) for path in current_map.keys() - previous_map.keys())
    removed = sorted(str(path) for path in previous_map.keys() - current_map.keys())
    changed = sorted(
        str(path)
        for path in current_map.keys() & previous_map.keys()
        if current_map[path].package_hash != previous_map[path].package_hash
    )
    return {"added": added, "removed": removed, "changed": changed}


def sparse_checkout(index: RepositoryIndex, repository_dir: Path, targets: Iterable[Path]) -> Dict[str, Path]:
    results: Dict[str, Path] = {}
    mirror_dir = repository_dir / "mirror"
    for target in targets:
        key = str(target)
        for entry in index.entries:
            if str(entry.source) == key:
                mirror_rel = entry.source.parent / f"{entry.source.name}.qyn1"
                results[key] = mirror_dir / mirror_rel
                break
    return results


__all__ = [
    "RepositoryEntry",
    "RepositoryIndex",
    "RepositoryWriter",
    "diff_repository_indexes",
    "load_repository_index",
    "sparse_checkout",
]

