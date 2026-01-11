"""Streaming utilities and buffers for low-memory encoding workflows."""

from __future__ import annotations

import mmap
import os
import tempfile
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional


class NullCollector(list):
    """List-like collector that drops appended items to save memory."""

    def append(self, value):  # type: ignore[override]
        return None

    def extend(self, values):  # type: ignore[override]
        return None


@dataclass
class ChunkMetadata:
    """Metadata describing a compressed token chunk."""

    offset: int
    length: int
    symbol_count: int
    frequencies: List[int]


class ChunkedTokenBuffer:
    """Append-only token buffer that spills to disk when exceeding memory limits."""

    def __init__(
        self,
        *,
        chunk_size: int = 65536,
        max_buffered_tokens: Optional[int] = None,
        directory: Optional[Path] = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._chunk_size = chunk_size
        if max_buffered_tokens is None:
            max_buffered_tokens = chunk_size
        if max_buffered_tokens <= 0:
            raise ValueError("max_buffered_tokens must be positive")
        self._max_buffered_tokens = max_buffered_tokens
        self._buffer = array("I")
        self._count = 0
        self._temp = tempfile.NamedTemporaryFile(dir=directory, delete=False)
        self._closed = False

    # ------------------------------------------------------------------
    # Collection protocol

    def append(self, value: int) -> None:
        self._buffer.append(value)
        self._count += 1
        if len(self._buffer) >= self._max_buffered_tokens:
            self._flush()

    def __len__(self) -> int:  # pragma: no cover - trivial
        return self._count

    def __iter__(self) -> Iterator[int]:
        yield from self.iter_tokens()

    # ------------------------------------------------------------------
    # Management helpers

    def _flush(self) -> None:
        if not self._buffer:
            return
        self._temp.write(self._buffer.tobytes())
        self._buffer = array("I")

    def close(self) -> None:
        if self._closed:
            return
        self._flush()
        self._temp.flush()
        self._temp.close()
        self._closed = True

    def dispose(self) -> None:
        try:
            os.remove(self._temp.name)
        except FileNotFoundError:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------
    # Iteration helpers

    def iter_tokens(self) -> Iterator[int]:
        for chunk in self.iter_chunks():
            for value in chunk:
                yield value

    def iter_chunks(self, chunk_size: Optional[int] = None) -> Iterator[array]:
        self.close()
        size = chunk_size or self._chunk_size
        with open(self._temp.name, "rb") as handle:
            while True:
                blob = handle.read(size * 4)
                if not blob:
                    break
                yield array("I", blob)

    def __del__(self) -> None:  # pragma: no cover - best effort cleanup
        try:
            self.close()
        except Exception:
            pass
        self.dispose()

    # ------------------------------------------------------------------
    # Context helpers

    def map_file(self, path: Path) -> mmap.mmap:
        """Return a memory map for the given file to enable streaming parse."""

        file = path.open("rb")
        return mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)


def iter_path_chunks(path: Path, chunk_size: int = 65536) -> Iterator[bytes]:
    """Yield bytes from a file in fixed size chunks."""

    with path.open("rb") as handle:
        while True:
            data = handle.read(chunk_size)
            if not data:
                break
            yield data


__all__ = [
    "ChunkMetadata",
    "ChunkedTokenBuffer",
    "NullCollector",
    "iter_path_chunks",
]
