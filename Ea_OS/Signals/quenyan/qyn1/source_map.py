"""Source map support for QYN-1 morphemic streams."""

from __future__ import annotations

import ast
import json
import zlib
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

SOURCE_MAP_VERSION = "1.0"


@dataclass
class SourceMapEntry:
    """Single mapping between a morpheme token and original source span."""

    token_index: int
    key: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    node_type: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token_index,
            "key": self.key,
            "start": [self.start_line, self.start_column],
            "end": [self.end_line, self.end_column],
            "node": self.node_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceMapEntry":
        start = data.get("start", [0, 0])
        end = data.get("end", [0, 0])
        return cls(
            token_index=int(data.get("token", 0)),
            key=str(data.get("key", "")),
            start_line=int(start[0]) if start else 0,
            start_column=int(start[1]) if len(start) > 1 else 0,
            end_line=int(end[0]) if end else 0,
            end_column=int(end[1]) if len(end) > 1 else 0,
            node_type=str(data.get("node", "unknown")),
        )


@dataclass
class SourceMap:
    """Collection of source map entries plus contextual metadata."""

    entries: List[SourceMapEntry]
    source_hash: str
    dictionary_version: str
    encoder_version: str
    version: str = SOURCE_MAP_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "source_hash": self.source_hash,
            "dictionary_version": self.dictionary_version,
            "encoder_version": self.encoder_version,
            "mappings": [entry.to_dict() for entry in self.entries],
        }

    def to_bytes(self) -> bytes:
        """Serialize the source map into a compact binary form."""

        payload = json.dumps(self.to_dict(), separators=(",", ":"))
        return zlib.compress(payload.encode("utf-8"))

    def write(self, path: str) -> None:
        with open(path, "wb") as handle:
            handle.write(self.to_bytes())

    def summary(self) -> Dict[str, Any]:
        """Return an aggregate view useful for inspectors."""

        return {
            "version": self.version,
            "entries": len(self.entries),
            "source_hash": self.source_hash,
            "dictionary_version": self.dictionary_version,
            "encoder_version": self.encoder_version,
        }

    @classmethod
    def from_bytes(cls, data: bytes) -> "SourceMap":
        decoded = json.loads(zlib.decompress(data).decode("utf-8"))
        return cls.from_dict(decoded)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceMap":
        mappings = [SourceMapEntry.from_dict(item) for item in data.get("mappings", [])]
        return cls(
            entries=mappings,
            source_hash=str(data.get("source_hash", "")),
            dictionary_version=str(data.get("dictionary_version", "unknown")),
            encoder_version=str(data.get("encoder_version", "unknown")),
            version=str(data.get("version", SOURCE_MAP_VERSION)),
        )


@dataclass
class SourceMapBuilder:
    """Helper that captures token locations during encoding."""

    entries: List[SourceMapEntry] = field(default_factory=list)

    def record(self, token_index: int, key: str, node: Optional[ast.AST]) -> None:
        if node is None:
            entry = SourceMapEntry(
                token_index=token_index,
                key=key,
                start_line=0,
                start_column=0,
                end_line=0,
                end_column=0,
                node_type="synthetic",
            )
            self.entries.append(entry)
            return
        start_line = getattr(node, "lineno", 0) or 0
        start_col = getattr(node, "col_offset", 0) or 0
        end_line = getattr(node, "end_lineno", start_line) or start_line
        end_col = getattr(node, "end_col_offset", start_col) or start_col
        entry = SourceMapEntry(
            token_index=token_index,
            key=key,
            start_line=start_line,
            start_column=start_col,
            end_line=end_line,
            end_column=end_col,
            node_type=type(node).__name__,
        )
        self.entries.append(entry)

    def build(
        self,
        source_hash: str,
        dictionary_version: str,
        encoder_version: str,
    ) -> SourceMap:
        return SourceMap(
            entries=list(self.entries),
            source_hash=source_hash,
            dictionary_version=dictionary_version,
            encoder_version=encoder_version,
        )
