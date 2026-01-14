"""Incremental encoding helpers for CI/CD pipelines."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, MutableMapping, Optional, Sequence, Set

from .compression_config import CompressionConfig, get_compression_config
from .encoder import EncodedStream, QYNEncoder
from .package import encode_package
from .pipeline import EncodingResult
from .project_compression import ProjectCompressionPlanner
from .streaming import ChunkedTokenBuffer, NullCollector
from .string_table import StringTable
from .token_optimisation import TokenOptimisationPlan


def _hash_bytes(blob: bytes) -> str:
    hasher = hashlib.sha256()
    hasher.update(blob)
    return hasher.hexdigest()


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            if chunk:
                hasher.update(chunk)
            else:
                break
    return hasher.hexdigest()


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


@dataclass
class CacheRecord:
    """Metadata stored for each cached source file."""

    content_hash: str
    package_hash: str
    output_bytes: int
    backend: str
    compression_mode: str
    dependencies: Dict[str, str]
    plan_digest: Optional[str]
    timestamp: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "content_hash": self.content_hash,
            "package_hash": self.package_hash,
            "output_bytes": self.output_bytes,
            "backend": self.backend,
            "compression_mode": self.compression_mode,
            "dependencies": self.dependencies,
            "plan_digest": self.plan_digest,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "CacheRecord":
        return cls(
            content_hash=str(data["content_hash"]),
            package_hash=str(data["package_hash"]),
            output_bytes=int(data.get("output_bytes", 0)),
            backend=str(data.get("backend", "")),
            compression_mode=str(data.get("compression_mode", "balanced")),
            dependencies={str(k): str(v) for k, v in dict(data.get("dependencies", {})).items()},
            plan_digest=(data.get("plan_digest") if data.get("plan_digest") else None),
            timestamp=float(data.get("timestamp", 0.0)),
        )


class IncrementalCache:
    """Disk-backed storage for previously encoded artefacts."""

    VERSION = 1

    def __init__(self, root: Path, directory: Path) -> None:
        self._root = root.resolve()
        self._directory = directory
        self._index_path = directory / "index.json"
        self._package_dir = directory / "packages"
        self._records: Dict[str, CacheRecord] = {}
        self._metadata: Dict[str, object] = {}
        if self._index_path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Serialisation helpers

    def _load(self) -> None:
        data = json.loads(self._index_path.read_text(encoding="utf-8"))
        version = data.get("version", 0)
        if version != self.VERSION:
            raise ValueError(
                f"Incremental cache version mismatch: expected {self.VERSION}, got {version}"
            )
        records = {}
        for key, payload in data.get("records", {}).items():
            records[str(key)] = CacheRecord.from_dict(payload)
        self._records = records
        self._metadata = data.get("metadata", {})

    def save(self) -> None:
        payload = {
            "version": self.VERSION,
            "records": {key: record.to_dict() for key, record in self._records.items()},
            "metadata": self._metadata,
        }
        self._directory.mkdir(parents=True, exist_ok=True)
        tmp_path = self._index_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self._index_path)

    # ------------------------------------------------------------------
    # Record management

    def get(self, path: Path) -> Optional[CacheRecord]:
        key = _relative(path, self._root)
        return self._records.get(key)

    def put(self, path: Path, record: CacheRecord) -> None:
        key = _relative(path, self._root)
        self._records[key] = record

    def update_timestamp(self, path: Path) -> None:
        record = self.get(path)
        if record:
            record.timestamp = time.time()

    # ------------------------------------------------------------------
    # Package storage

    def store_package(self, blob: bytes) -> str:
        digest = _hash_bytes(blob)
        destination = self._package_dir / f"{digest}.qyn1"
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            tmp = destination.with_suffix(".tmp")
            tmp.write_bytes(blob)
            os.replace(tmp, destination)
        return digest

    def retrieve_package(self, package_hash: str) -> bytes:
        path = self._package_dir / f"{package_hash}.qyn1"
        return path.read_bytes()

    def copy_package(self, package_hash: str, destination: Path) -> None:
        source = self._package_dir / f"{package_hash}.qyn1"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    # ------------------------------------------------------------------

    @property
    def metadata(self) -> MutableMapping[str, object]:
        return self._metadata


class DependencyResolver:
    """Resolve on-disk dependencies for source files."""

    def dependencies_for(self, path: Path) -> Sequence[Path]:
        return []


class ManifestDependencyResolver(DependencyResolver):
    """Look up dependencies from a static manifest."""

    def __init__(self, manifest: Mapping[str, Sequence[str]], root: Path) -> None:
        self._root = root.resolve()
        self._manifest = {
            str(key): [str(item) for item in value]
            for key, value in manifest.items()
        }

    def dependencies_for(self, path: Path) -> Sequence[Path]:
        key = _relative(path, self._root)
        entries = self._manifest.get(key, [])
        return [self._root / entry for entry in entries]


class PythonImportResolver(DependencyResolver):
    """Best-effort dependency resolver for Python modules."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _candidate_paths(self, module: str) -> List[Path]:
        parts = module.split(".")
        relative = Path(*parts)
        candidates = [relative.with_suffix(".py"), relative / "__init__.py"]
        return [self._root / candidate for candidate in candidates]

    def dependencies_for(self, path: Path) -> Sequence[Path]:
        if path.suffix != ".py":
            return []
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            return []
        import ast

        try:
            module = ast.parse(source)
        except SyntaxError:
            return []
        dependencies: Set[Path] = set()
        for node in module.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for candidate in self._candidate_paths(alias.name):
                        if candidate.exists():
                            dependencies.add(candidate)
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                base = node.module
                for candidate in self._candidate_paths(base):
                    if candidate.exists():
                        dependencies.add(candidate)
        return sorted(dependencies)


class HybridDependencyResolver(DependencyResolver):
    """Combine manifest data with heuristic resolvers."""

    def __init__(self, root: Path, manifest: Optional[Mapping[str, Sequence[str]]] = None) -> None:
        self._root = root.resolve()
        self._manifest = ManifestDependencyResolver(manifest or {}, self._root)
        self._python = PythonImportResolver(self._root)

    def dependencies_for(self, path: Path) -> Sequence[Path]:
        seen: Dict[str, Path] = {}
        for dep in self._manifest.dependencies_for(path):
            seen[_relative(dep, self._root)] = dep
        for dep in self._python.dependencies_for(path):
            seen.setdefault(_relative(dep, self._root), dep)
        return sorted(seen.values())


@dataclass
class IncrementalReport:
    """Summary information for an incremental build."""

    encoded: List[EncodingResult]
    reused: List[Path]
    skipped: List[Path]
    cache_hits: int
    cache_misses: int
    dependency_rebuilds: int
    total_duration_s: float
    plan_digest: Optional[str]

    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if not total:
            return 0.0
        return self.cache_hits / total

    def to_dict(self) -> Dict[str, object]:
        return {
            "encoded": [
                {
                    "source": str(item.source),
                    "output": str(item.output),
                    "duration_s": item.duration_s,
                    "input_bytes": item.input_bytes,
                    "output_bytes": item.output_bytes,
                    "backend": item.backend,
                    "streaming": item.streaming,
                }
                for item in self.encoded
            ],
            "reused": [str(path) for path in self.reused],
            "skipped": [str(path) for path in self.skipped],
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "dependency_rebuilds": self.dependency_rebuilds,
            "total_duration_s": self.total_duration_s,
            "cache_hit_rate": self.hit_rate(),
            "plan_digest": self.plan_digest,
        }


class IncrementalEncoder:
    """High-level orchestration for incremental encoding runs."""

    def __init__(
        self,
        *,
        root: Path,
        sources: Sequence[Path],
        output_dir: Path,
        cache_dir: Path,
        passphrase: str,
        compression_config: Optional[CompressionConfig] = None,
        backend_override: Optional[str] = None,
        dependency_resolver: Optional[DependencyResolver] = None,
        streaming_threshold: int = 32 * 1024 * 1024,
        chunk_size: int = 65536,
        max_buffered_tokens: int = 65536,
        strict_morpheme_errors: bool = False,
        shard_index: int = 0,
        shard_count: int = 1,
    ) -> None:
        self._root = root.resolve()
        self._sources = [path.resolve() for path in sources]
        self._output_dir = output_dir
        self._cache = IncrementalCache(self._root, cache_dir)
        self._passphrase = passphrase
        self._config = compression_config or get_compression_config(None)
        if backend_override and backend_override != "preset":
            self._config = self._config.with_backend(backend_override)
        self._backend = backend_override if backend_override and backend_override != "preset" else self._config.backend
        self._dependency_resolver = dependency_resolver or HybridDependencyResolver(self._root)
        self._streaming_threshold = streaming_threshold
        self._chunk_size = chunk_size
        self._max_buffered_tokens = max_buffered_tokens
        self._strict_morpheme_errors = strict_morpheme_errors
        if shard_count < 1:
            raise ValueError("shard_count must be >= 1")
        if shard_index < 0 or shard_index >= shard_count:
            raise ValueError("shard_index must be within [0, shard_count)")
        self._shard_index = shard_index
        self._shard_count = shard_count

    # ------------------------------------------------------------------
    # Public API

    def run(self) -> IncrementalReport:
        start = time.perf_counter()
        plan_digest: Optional[str] = None
        plan_assets = None
        if self._config.wants_project_planning():
            planner = ProjectCompressionPlanner(
                self._config,
                encoder_factory=self._build_encoder,
            )
            plan = planner.prepare(self._sources)
            digest = hashlib.sha256()
            assets = plan.assets
            if assets.string_table is not None:
                digest.update(assets.string_table.to_bytes())
            if assets.token_plan is not None:
                digest.update(bytes(assets.token_plan.dense_to_original))
            digest.update(self._backend.encode("utf-8"))
            plan_digest = digest.hexdigest()
            streams = plan.streams
            plan_assets = assets
        else:
            streams = {}

        encoded_results: List[EncodingResult] = []
        reused: List[Path] = []
        skipped: List[Path] = []
        cache_hits = 0
        cache_misses = 0
        dependency_rebuilds = 0

        for path in sorted(self._sources):
            if (hash(_relative(path, self._root)) % self._shard_count) != self._shard_index:
                skipped.append(path)
                continue
            dependencies = list(self._dependency_resolver.dependencies_for(path))
            dependency_hashes = {
                _relative(dep, self._root): _hash_file(dep) for dep in dependencies if dep.exists()
            }
            content_hash = _hash_file(path)
            record = self._cache.get(path)
            needs_rebuild = False
            if record is None:
                needs_rebuild = True
            else:
                if record.content_hash != content_hash:
                    needs_rebuild = True
                elif record.plan_digest != plan_digest:
                    needs_rebuild = True
                else:
                    for dep_key, dep_hash in dependency_hashes.items():
                        if record.dependencies.get(dep_key) != dep_hash:
                            dependency_rebuilds += 1
                            needs_rebuild = True
                            break
            if not needs_rebuild and record is not None:
                cache_hits += 1
                self._cache.update_timestamp(path)
                output_path = self._output_dir / f"{path.stem}.qyn1"
                self._cache.copy_package(record.package_hash, output_path)
                reused.append(path)
                continue

            result = self._encode_file(
                path,
                dependencies=dependency_hashes,
                plan_stream=streams.get(path),
                plan_digest=plan_digest,
                content_hash=content_hash,
                string_table=plan_assets.string_table if plan_assets else None,
                token_plan=plan_assets.token_plan if plan_assets else None,
            )
            encoded_results.append(result)
            cache_misses += 1

        self._cache.save()
        duration = time.perf_counter() - start
        return IncrementalReport(
            encoded=encoded_results,
            reused=reused,
            skipped=skipped,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            dependency_rebuilds=dependency_rebuilds,
            total_duration_s=duration,
            plan_digest=plan_digest,
        )

    # ------------------------------------------------------------------
    # Internal helpers

    def _encode_file(
        self,
        path: Path,
        *,
        dependencies: Dict[str, str],
        plan_stream: Optional[EncodedStream],
        plan_digest: Optional[str],
        content_hash: str,
        string_table: Optional[StringTable],
        token_plan: Optional[TokenOptimisationPlan],
    ) -> EncodingResult:
        file_size = path.stat().st_size
        use_streaming = file_size >= self._streaming_threshold
        encoder = self._build_encoder()
        token_buffer: Optional[ChunkedTokenBuffer] = None
        human_buffer = NullCollector()
        start = time.perf_counter()
        try:
            if plan_stream is not None:
                stream = plan_stream
            elif use_streaming:
                token_buffer = ChunkedTokenBuffer(
                    chunk_size=self._chunk_size,
                    max_buffered_tokens=self._max_buffered_tokens,
                )
                with path.open("rb") as handle:
                    data = handle.read()
                stream = encoder.encode(data, token_buffer=token_buffer, human_buffer=human_buffer)
                token_buffer.close()
            else:
                data = path.read_bytes()
                stream = encoder.encode(data)
        finally:
            end = time.perf_counter()
        duration = end - start

        package = encode_package(
            stream,
            backend_name=self._backend,
            compression=self._config.with_backend(self._backend),
            string_table=string_table,
            token_plan=token_plan,
        )
        blob = package.to_bytes(self._passphrase)
        output_path = self._output_dir / f"{path.stem}.qyn1"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(blob)

        package_hash = self._cache.store_package(blob)
        record = CacheRecord(
            content_hash=content_hash,
            package_hash=package_hash,
            output_bytes=len(blob),
            backend=self._backend,
            compression_mode=self._config.mode,
            dependencies=dependencies,
            plan_digest=plan_digest,
            timestamp=time.time(),
        )
        self._cache.put(path, record)
        if token_buffer is not None:
            token_buffer.dispose()
        return EncodingResult(
            source=path,
            output=output_path,
            duration_s=duration,
            input_bytes=file_size,
            output_bytes=len(blob),
            backend=self._backend,
            streaming=use_streaming,
        )

    def _build_encoder(self) -> QYNEncoder:
        return QYNEncoder(strict_morpheme_errors=self._strict_morpheme_errors)


__all__ = [
    "CacheRecord",
    "DependencyResolver",
    "HybridDependencyResolver",
    "IncrementalCache",
    "IncrementalEncoder",
    "IncrementalReport",
    "ManifestDependencyResolver",
    "PythonImportResolver",
]
