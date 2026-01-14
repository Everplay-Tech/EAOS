"""Benchmark harness and dataset utilities for the Quenyan suite."""

from __future__ import annotations

import gzip
import json
import tarfile
import time
import tracemalloc
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
from urllib.request import urlopen

from .compression_config import CompressionConfig, get_compression_config
from .decoder import QYNDecoder
from .encoder import QYNEncoder
from .package import decode_package, encode_package


class UnsupportedLanguageError(RuntimeError):
    """Raised when a dataset requests a language the runner cannot process."""


@dataclass(frozen=True)
class DownloadSpec:
    url: str
    sha256: Optional[str] = None
    archive_subdir: Optional[str] = None


@dataclass(frozen=True)
class DatasetDescriptor:
    slug: str
    name: str
    category: str
    language: str
    domain: str
    estimated_loc: int
    description: str
    entry_glob: Sequence[str]
    download: Optional[DownloadSpec] = None
    local_fixture: Optional[str] = None

    @property
    def size_bucket(self) -> str:
        return self.category


@dataclass
class FileBenchmark:
    source_path: Path
    encoded_path: Path
    input_bytes: int
    gzip_bytes: int
    encoded_bytes: int
    compressed_bytes: int


@dataclass
class BenchmarkSummary:
    dataset: DatasetDescriptor
    files: List[FileBenchmark]
    encode_seconds: float
    decode_seconds: float
    encode_peak_bytes: int
    decode_peak_bytes: int

    @property
    def total_input_bytes(self) -> int:
        return sum(item.input_bytes for item in self.files)

    @property
    def total_encoded_bytes(self) -> int:
        return sum(item.encoded_bytes for item in self.files)

    @property
    def total_gzip_bytes(self) -> int:
        return sum(item.gzip_bytes for item in self.files)

    @property
    def total_overhead_bytes(self) -> int:
        return sum(item.encoded_bytes - item.compressed_bytes for item in self.files)

    def to_dict(self) -> Dict[str, object]:
        return {
            "slug": self.dataset.slug,
            "category": self.dataset.category,
            "language": self.dataset.language,
            "domain": self.dataset.domain,
            "encode_seconds": self.encode_seconds,
            "decode_seconds": self.decode_seconds,
            "encode_peak_bytes": self.encode_peak_bytes,
            "decode_peak_bytes": self.decode_peak_bytes,
            "total_input_bytes": self.total_input_bytes,
            "total_encoded_bytes": self.total_encoded_bytes,
            "total_gzip_bytes": self.total_gzip_bytes,
            "compression_ratio_vs_source": (
                self.total_encoded_bytes / self.total_input_bytes
                if self.total_input_bytes
                else 0.0
            ),
            "compression_ratio_vs_gzip": (
                self.total_encoded_bytes / self.total_gzip_bytes
                if self.total_gzip_bytes
                else 0.0
            ),
            "mcs_overhead_bytes": self.total_overhead_bytes,
            "file_count": len(self.files),
        }


def load_manifest(path: Path) -> List[DatasetDescriptor]:
    data = json.loads(path.read_text())
    datasets: List[DatasetDescriptor] = []
    for entry in data.get("datasets", []):
        download_spec = None
        raw_download = entry.get("download")
        if raw_download:
            download_spec = DownloadSpec(
                url=raw_download.get("url", ""),
                sha256=raw_download.get("sha256"),
                archive_subdir=raw_download.get("archive_subdir"),
            )
        descriptor = DatasetDescriptor(
            slug=entry["slug"],
            name=entry["name"],
            category=entry["category"],
            language=entry["language"],
            domain=entry["domain"],
            estimated_loc=int(entry.get("estimated_loc", 0)),
            description=entry.get("description", ""),
            entry_glob=tuple(entry.get("entry_glob", ["**/*.py"])),
            download=download_spec,
            local_fixture=entry.get("local_fixture"),
        )
        datasets.append(descriptor)
    return datasets


def _download_archive(dataset: DatasetDescriptor, destination: Path) -> Path:
    if dataset.download is None:
        raise ValueError(f"Dataset {dataset.slug} does not define a download source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return destination
    with urlopen(dataset.download.url) as response:  # pragma: no cover - network
        destination.write_bytes(response.read())  # pragma: no cover - network
    return destination


def _extract_archive(archive: Path, target_dir: Path, subdir: Optional[str]) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target_dir)
    elif archive.suffixes[-2:] == [".tar", ".gz"] or archive.suffixes[-1] == ".tgz":
        with tarfile.open(archive) as tf:
            tf.extractall(target_dir)
    else:
        raise ValueError(f"Unsupported archive type for {archive}")
    root = target_dir
    if subdir:
        root = target_dir / subdir
    return root


def resolve_dataset(descriptor: DatasetDescriptor, workspace: Path) -> Path:
    if descriptor.local_fixture:
        local_path = Path(descriptor.local_fixture)
        if not local_path.is_absolute():
            local_path = Path(__file__).resolve().parents[1] / descriptor.local_fixture
        return local_path
    if descriptor.download is None:
        raise ValueError(f"Dataset {descriptor.slug} does not define a download source")
    downloads_dir = workspace / "downloads"
    archives_dir = downloads_dir / "archives"
    extracted_dir = downloads_dir / "extracted"
    archive_suffix = Path(descriptor.download.url).suffix or ".zip"
    archive_path = archives_dir / f"{descriptor.slug}{archive_suffix}"
    _download_archive(descriptor, archive_path)
    return _extract_archive(
        archive_path, extracted_dir / descriptor.slug, descriptor.download.archive_subdir
    )


def _discover_python_sources(root: Path, patterns: Sequence[str]) -> List[Path]:
    sources: List[Path] = []
    for pattern in patterns:
        sources.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted({path.resolve() for path in sources})


def _measure(func):
    tracemalloc.start()
    start = time.perf_counter()
    result = func()
    duration = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, duration, peak


def benchmark_dataset(
    descriptor: DatasetDescriptor,
    *,
    workspace: Path,
    output_dir: Path,
    passphrase: str,
    compression: Optional[CompressionConfig] = None,
) -> BenchmarkSummary:
    if descriptor.language.lower() != "python":
        raise UnsupportedLanguageError(descriptor.language)

    root = resolve_dataset(descriptor, workspace)
    sources = _discover_python_sources(root, descriptor.entry_glob)
    encoder = QYNEncoder()
    config = compression or get_compression_config(None)
    packages: List[FileBenchmark] = []
    output_root = output_dir / descriptor.slug
    output_root.mkdir(parents=True, exist_ok=True)

    def encode_all() -> None:
        for source_path in sources:
            data = source_path.read_bytes()
            stream = encoder.encode(data)
            package = encode_package(stream, config.backend, compression=config)
            package_bytes = package.to_bytes(passphrase)
            relative = source_path.relative_to(root)
            encoded_path = output_root / relative.with_suffix(".qyn1")
            encoded_path.parent.mkdir(parents=True, exist_ok=True)
            encoded_path.write_bytes(package_bytes)
            packages.append(
                FileBenchmark(
                    source_path=source_path,
                    encoded_path=encoded_path,
                    input_bytes=len(data),
                    gzip_bytes=len(gzip.compress(data)),
                    encoded_bytes=len(package_bytes),
                    compressed_bytes=len(package.compressed_tokens),
                )
            )

    _, encode_duration, encode_peak = _measure(encode_all)

    def decode_all() -> None:
        for item in packages:
            payload = item.encoded_path.read_bytes()
            stream = decode_package(payload, passphrase)
            decoder = QYNDecoder(
                stream.dictionary,
                stream.tokens,
                stream.payloads,
                payload_channels=stream.payload_channels,
            )
            decoder.decode()

    _, decode_duration, decode_peak = _measure(decode_all)

    return BenchmarkSummary(
        dataset=descriptor,
        files=packages,
        encode_seconds=encode_duration,
        decode_seconds=decode_duration,
        encode_peak_bytes=encode_peak,
        decode_peak_bytes=decode_peak,
    )


def summarise_to_json(results: Iterable[BenchmarkSummary]) -> List[Dict[str, object]]:
    return [summary.to_dict() for summary in results]
