"""Public API for the QYN-1 encoder/decoder toolkit."""

from __future__ import annotations

from .compression import available_backends, get_backend
from .decoder import QYNDecoder
from .encoder import EncodedStream, QYNEncoder
from .package import decode_package, encode_package, read_package
from .source_map import SourceMap, SourceMapEntry
from .streaming import ChunkedTokenBuffer, NullCollector

__all__ = [
    "available_backends",
    "get_backend",
    "QYNDecoder",
    "EncodedStream",
    "QYNEncoder",
    "encode_package",
    "decode_package",
    "read_package",
    "SourceMap",
    "SourceMapEntry",
    "ChunkedTokenBuffer",
    "NullCollector",
]
