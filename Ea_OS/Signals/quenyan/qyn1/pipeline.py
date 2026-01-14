"""High level encoding pipelines including parallel and streaming workflows."""

from __future__ import annotations

import concurrent.futures
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .compression_config import CompressionConfig, get_compression_config
from .encoder import QYNEncoder
from .encoding_io import encode_file_with_options
from .io import ChunkedSource, ChunkedSourceConfig
from .package import _extract_wrapper_components, encode_package
from .language_detection import detect_language
from .project_compression import ProjectCompressionPlanner
from .streaming import ChunkedTokenBuffer, NullCollector


@dataclass
class EncodingResult:
    """Summary statistics produced after encoding a single file."""

    source: Path
    output: Path
    duration_s: float
    input_bytes: int
    output_bytes: int
    backend: str
    streaming: bool


@dataclass
class ProjectEncodingReport:
    """Aggregate report produced by the parallel encoder."""

    results: List[EncodingResult]
    total_duration_s: float

    @property
    def total_input_bytes(self) -> int:
        return sum(result.input_bytes for result in self.results)

    @property
    def total_output_bytes(self) -> int:
        return sum(result.output_bytes for result in self.results)

    @property
    def average_throughput_mb_s(self) -> float:
        if not self.total_duration_s:
            return 0.0
        return (self.total_input_bytes / 1_048_576) / self.total_duration_s


@dataclass
class EncodingJob:
    path: Path
    output: Path
    passphrase: str
    backend: str
    strict_morpheme_errors: bool
    streaming_backend: str
    streaming_threshold: int
    chunk_size: int
    max_buffered_tokens: int
    compression_config: CompressionConfig
    tree_sitter_language: Optional[str] = None
    language_hint: Optional[str] = None


def _encode_file(job: EncodingJob) -> EncodingResult:
    encoder = QYNEncoder(strict_morpheme_errors=job.strict_morpheme_errors)
    file_size = job.path.stat().st_size
    use_streaming = file_size >= job.streaming_threshold
    backend_name = job.backend
    token_buffer: Optional[ChunkedTokenBuffer] = None
    start = time.perf_counter()
    detection = None
    try:
        if use_streaming:
            backend_name = job.streaming_backend
            token_buffer = ChunkedTokenBuffer(
                chunk_size=job.chunk_size, max_buffered_tokens=job.max_buffered_tokens
            )
            human_buffer = NullCollector()
            detection = detect_language(job.path, None, language_hint=job.language_hint, default=encoder.language_profile_name)
            encoder.language_profile = detection.profile
            encoder.language_profile_name = detection.profile.name
            chunk_config = ChunkedSourceConfig(
                chunk_size=job.chunk_size,
                tree_sitter_language=job.tree_sitter_language,
            )
            source = ChunkedSource(job.path, config=chunk_config)
            stream = encoder.encode(
                source, token_buffer=token_buffer, human_buffer=human_buffer
            )
            token_buffer.close()
        else:
            stream, detection = encode_file_with_options(
                job.path,
                encoder,
                language_hint=job.language_hint,
            )
    finally:
        end = time.perf_counter()
    duration = end - start

    active_backend = backend_name
    backend_options = {} if active_backend != job.compression_config.backend else None
    config = job.compression_config.with_backend(active_backend, backend_options=backend_options)
    try:
        package = encode_package(stream, active_backend, compression=config)
    finally:
        if token_buffer is not None:
            token_buffer.dispose()

    blob = package.to_bytes(job.passphrase)
    job.output.parent.mkdir(parents=True, exist_ok=True)
    job.output.write_bytes(blob)
    wrapped_output = PackagePath(job.output)
    return EncodingResult(
        source=job.path,
        output=wrapped_output,
        duration_s=duration,
        input_bytes=file_size,
        output_bytes=len(blob),
        backend=active_backend,
        streaming=use_streaming,
    )


def encode_project(
    sources: Iterable[Path],
    output_dir: Path,
    passphrase: str,
    *,
    backend: str = "fse-production",
    strict_morpheme_errors: bool = False,
    streaming_backend: str = "chunked-rans",
    streaming_threshold: int = 32 * 1024 * 1024,
    chunk_size: int = 65536,
    max_buffered_tokens: int = 65536,
    max_workers: Optional[int] = None,
    compression_config: Optional[CompressionConfig] = None,
    tree_sitter_language: Optional[str] = None,
    language_hint: Optional[str] = None,
) -> ProjectEncodingReport:
    """Encode multiple files in parallel, returning a report of the results."""

    sources = list(sources)
    if compression_config is None:
        config = get_compression_config(None).with_backend(backend)
    else:
        config = compression_config

    selected_backend = backend if compression_config is None else config.backend

    if config.wants_project_planning():
        planner = ProjectCompressionPlanner(
            config,
            encoder_factory=lambda: QYNEncoder(strict_morpheme_errors=strict_morpheme_errors),
        )
        plan = planner.prepare(sources)
        results: List[EncodingResult] = []
        start = time.perf_counter()
        for path in sources:
            stream = plan.streams[path]
            output_path = output_dir / f"{path.stem}.qyn1"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            encode_start = time.perf_counter()
            package = encode_package(
                stream,
                config.backend,
                compression=config,
                string_table=plan.assets.string_table,
                token_plan=plan.assets.token_plan,
            )
            blob = package.to_bytes(passphrase)
            output_path.write_bytes(blob)
            duration = time.perf_counter() - encode_start
            results.append(
                EncodingResult(
                    source=path,
                    output=PackagePath(output_path),
                    duration_s=duration,
                    input_bytes=path.stat().st_size,
                    output_bytes=len(blob),
                    backend=config.backend,
                    streaming=False,
                )
            )
        total_duration = time.perf_counter() - start
        results.sort(key=lambda item: item.source)
        return ProjectEncodingReport(results=results, total_duration_s=total_duration)

    jobs = [
        EncodingJob(
            path=path,
            output=output_dir / f"{path.stem}.qyn1",
            passphrase=passphrase,
            backend=selected_backend,
            streaming_backend=streaming_backend,
            streaming_threshold=streaming_threshold,
            chunk_size=chunk_size,
            max_buffered_tokens=max_buffered_tokens,
            compression_config=config,
            strict_morpheme_errors=strict_morpheme_errors,
            tree_sitter_language=tree_sitter_language,
            language_hint=language_hint,
        )
        for path in sources
    ]

    results: List[EncodingResult] = []
    start = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_encode_file, job): job for job in jobs}
        for future in concurrent.futures.as_completed(future_map):
            results.append(future.result())
    total_duration = time.perf_counter() - start
    results.sort(key=lambda item: item.source)
    return ProjectEncodingReport(results=results, total_duration_s=total_duration)


__all__ = [
    "EncodingResult",
    "EncodingJob",
    "ProjectEncodingReport",
    "encode_project",
]
class PackagePath(type(Path())):
    """Path subclass that exposes wrapper JSON when read as text."""

    def read_text(self, *args, **kwargs):  # type: ignore[override]
        if "encoding" not in kwargs:
            kwargs["encoding"] = "utf-8"
        raw = super().read_bytes()
        try:
            structured, _, wrapper, _ = _extract_wrapper_components(raw)
        except Exception:
            return super().read_text(*args, **kwargs)
        if structured:
            return json.dumps(wrapper)
        return super().read_text(*args, **kwargs)
