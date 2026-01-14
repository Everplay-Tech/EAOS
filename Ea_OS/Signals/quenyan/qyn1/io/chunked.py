"""Chunked source readers that feed incremental AST builders."""

from __future__ import annotations

import ast
import importlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Protocol

DEFAULT_CHUNK_SIZE = 262_144  # 256 KiB


@dataclass(frozen=True)
class ChunkedSourceConfig:
    """Configuration values controlling chunked source streaming."""

    chunk_size: int = DEFAULT_CHUNK_SIZE
    encoding: str = "utf-8"
    incremental: bool = True
    tree_sitter_language: Optional[str] = None
    max_spool_bytes: int = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.max_spool_bytes <= 0:
            raise ValueError("max_spool_bytes must be positive")


class IncrementalASTBuilder(Protocol):
    """Protocol implemented by incremental AST builders."""

    encoding: str

    def push_bytes(self, data: bytes) -> None:
        ...

    def finish(self) -> ast.AST:
        ...


class PythonBufferedASTBuilder:
    """Incremental builder that spools bytes to disk before parsing."""

    def __init__(self, *, encoding: str = "utf-8", max_spool_bytes: int = 16 * 1024 * 1024) -> None:
        self.encoding = encoding
        self._buffer: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(
            max_size=max_spool_bytes
        )

    def push_bytes(self, data: bytes) -> None:
        self._buffer.write(data)

    def finish(self) -> ast.AST:
        self._buffer.seek(0)
        source = self._buffer.read().decode(self.encoding)
        module = ast.parse(source)
        ast.fix_missing_locations(module)
        return module


class TreeSitterIncrementalBuilder:
    """Incremental builder backed by a Tree-sitter push parser."""

    def __init__(self, language: str, *, encoding: str = "utf-8") -> None:
        spec = importlib.util.find_spec("tree_sitter")
        if spec is None:
            raise RuntimeError("tree_sitter package is required for TreeSitterIncrementalBuilder")
        tree_sitter = importlib.import_module("tree_sitter")
        language_module = importlib.import_module(language)
        parser = tree_sitter.Parser()
        parser.set_language(language_module.LANGUAGE)
        self._parser = parser
        self.encoding = encoding
        self._tree = None
        self._chunks: bytearray = bytearray()

    def push_bytes(self, data: bytes) -> None:
        self._chunks.extend(data)
        self._tree = self._parser.parse(bytes(self._chunks), self._tree)

    def finish(self) -> ast.AST:
        # When Tree-sitter is available we still need a Python AST for the encoder.
        # We fall back to the standard library parser for the final conversion while
        # reusing the bytes accumulated via incremental parsing.
        module = ast.parse(bytes(self._chunks).decode(self.encoding))
        ast.fix_missing_locations(module)
        return module


class ChunkedSourceReader:
    """Read sources in fixed-size chunks and feed an incremental builder."""

    def __init__(self, builder: IncrementalASTBuilder, config: ChunkedSourceConfig) -> None:
        self._builder = builder
        self._config = config

    def read(self, handle: BinaryIO) -> ast.AST:
        for chunk in iter(lambda: handle.read(self._config.chunk_size), b""):
            if not chunk:
                break
            self._builder.push_bytes(chunk)
        return self._builder.finish()


class ChunkedSource:
    """Helper for constructing ASTs from on-disk files without materialising them."""

    def __init__(self, path: Path, *, config: Optional[ChunkedSourceConfig] = None) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        self._path = path
        self._config = config or ChunkedSourceConfig()

    @property
    def path(self) -> Path:
        return self._path

    def ast(self) -> ast.AST:
        builder = self._select_builder()
        reader = ChunkedSourceReader(builder, self._config)
        with self._path.open("rb") as handle:
            return reader.read(handle)

    def _select_builder(self) -> IncrementalASTBuilder:
        if self._config.incremental and self._config.tree_sitter_language:
            return TreeSitterIncrementalBuilder(
                self._config.tree_sitter_language, encoding=self._config.encoding
            )
        return PythonBufferedASTBuilder(
            encoding=self._config.encoding, max_spool_bytes=self._config.max_spool_bytes
        )

    def iter_bytes(self) -> Iterator[bytes]:
        chunk_size = self._config.chunk_size
        with self._path.open("rb") as handle:
            while True:
                blob = handle.read(chunk_size)
                if not blob:
                    break
                yield blob

    def to_bytes(self) -> bytes:
        return b"".join(self.iter_bytes())


__all__ = [
    "ChunkedSource",
    "ChunkedSourceConfig",
    "ChunkedSourceReader",
    "IncrementalASTBuilder",
    "PythonBufferedASTBuilder",
    "TreeSitterIncrementalBuilder",
]
