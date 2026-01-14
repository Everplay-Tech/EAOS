"""Frequency-aware string table with prefix compression for payload data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import re
from typing import Any, Dict, Iterable, List, Tuple

from .compression import RANSBackend

_SENTINEL_KEY = "__strref__"
_STRING_TABLE_VERSION = 1

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def _classify_string(value: str) -> int:
    """Return a small integer type identifier for the given string.

    The classifier is intentionally lightweight and relies on simple pattern
    checks so it can run across large corpora without introducing measurable
    overhead. The mapping is kept deliberately compact:

    0. Generic/unknown (fallback).
    1. Identifier-like tokens (alphanumeric and underscore only).
    2. Path or URL material (contains slashes or protocol markers).
    3. Natural language fragments (whitespace and punctuation heavy).
    4. Structured text such as JSON or SQL.
    """

    text = value.strip()
    if not text:
        return 0
    if _IDENTIFIER_PATTERN.match(text):
        return 1
    lowered = text.lower()
    if "://" in text or "/" in text or "\\" in text:
        return 2
    if lowered.startswith(("{", "[")) or lowered.startswith(("select", "insert", "update", "delete", "with")):
        return 4
    if any(ch.isspace() for ch in text) and any(not ch.isalnum() and not ch.isspace() for ch in text):
        return 3
    return 0


def _length_bucket(value: str) -> int:
    length = len(value)
    if length <= 8:
        return 0
    if length <= 32:
        return 1
    if length <= 128:
        return 2
    return 3


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)


def _longest_common_prefix(a: str, b: str) -> int:
    count = 0
    limit = min(len(a), len(b))
    for index in range(limit):
        if a[index] != b[index]:
            break
        count += 1
    return count


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint cannot encode negative values")
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            break
    return bytes(out)


def _decode_varint(buffer: bytes, offset: int) -> Tuple[int, int]:
    shift = 0
    result = 0
    while True:
        if offset >= len(buffer):
            raise ValueError("unterminated varint sequence")
        byte = buffer[offset]
        result |= (byte & 0x7F) << shift
        offset += 1
        if not byte & 0x80:
            break
        shift += 7
        if shift > 63:
            raise ValueError("varint is too large")
    return result, offset


@dataclass
class StringTableEntry:
    """Prefix-compressed description of a single string."""

    value: str
    frequency: int
    prefix_length: int
    suffix: str
    type_id: int
    length_bucket: int


class StringTable:
    """Frequency-aware string table with prefix compression."""

    def __init__(self, entries: List[StringTableEntry]):
        self._entries = entries
        self._index: Dict[str, int] = {entry.value: idx for idx, entry in enumerate(entries)}

    # ------------------------------------------------------------------
    # Construction helpers

    @classmethod
    def build_from_payloads(cls, payloads: Iterable[Any]) -> "StringTable":
        counter: Counter[str] = Counter()
        for payload in payloads:
            if hasattr(payload, "value"):
                counter.update(_iter_strings(payload.value))
            else:
                counter.update(_iter_strings(payload))
        if not counter:
            return cls([])
        ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        entries: List[StringTableEntry] = []
        previous = ""
        for value, frequency in ordered:
            prefix_length = _longest_common_prefix(previous, value)
            suffix = value[prefix_length:]
            type_id = _classify_string(value)
            length_bucket = _length_bucket(value)
            entries.append(
                StringTableEntry(
                    value=value,
                    frequency=frequency,
                    prefix_length=prefix_length,
                    suffix=suffix,
                    type_id=type_id,
                    length_bucket=length_bucket,
                )
            )
            previous = value
        return cls(entries)

    # ------------------------------------------------------------------
    # Lookup helpers

    def __len__(self) -> int:
        return len(self._entries)

    def index_for(self, value: str) -> int:
        try:
            return self._index[value]
        except KeyError as exc:
            raise KeyError(f"{value!r} is not present in the string table") from exc

    def string_for_index(self, index: int) -> str:
        return self._entries[index].value

    # ------------------------------------------------------------------
    # Encoding/decoding

    def to_bytes(self) -> bytes:
        buffer = bytearray()
        buffer.extend(_encode_varint(_STRING_TABLE_VERSION))
        buffer.extend(_encode_varint(len(self._entries)))

        grouped_suffix_bytes: Dict[int, List[int]] = {}
        metadata: List[Tuple[int, int, int, int, int]] = []
        for entry in self._entries:
            suffix_bytes = entry.suffix.encode("utf-8")
            metadata.append(
                (
                    entry.prefix_length,
                    len(suffix_bytes),
                    entry.frequency,
                    entry.type_id,
                    entry.length_bucket,
                )
            )
            grouped_suffix_bytes.setdefault(entry.type_id, []).extend(suffix_bytes)

        for prefix_length, suffix_len, frequency, type_id, length_bucket in metadata:
            buffer.extend(_encode_varint(prefix_length))
            buffer.extend(_encode_varint(suffix_len))
            buffer.extend(_encode_varint(frequency))
            buffer.extend(_encode_varint(type_id))
            buffer.extend(_encode_varint(length_bucket))

        backend = RANSBackend()
        buffer.extend(_encode_varint(len(grouped_suffix_bytes)))
        for type_id in sorted(grouped_suffix_bytes.keys()):
            raw_bytes = grouped_suffix_bytes[type_id]
            model = backend.build_model(raw_bytes, alphabet_size=256)
            compressed = backend.encode(raw_bytes, model)
            model_blob = json.dumps(model, sort_keys=True).encode("utf-8")

            buffer.extend(_encode_varint(type_id))
            buffer.extend(_encode_varint(len(raw_bytes)))
            buffer.extend(_encode_varint(len(model_blob)))
            buffer.extend(model_blob)
            buffer.extend(_encode_varint(len(compressed)))
            buffer.extend(compressed)
        return bytes(buffer)

    @classmethod
    def from_bytes(cls, data: bytes) -> "StringTable":
        try:
            return cls._from_bytes_v1(data)
        except Exception:
            return cls._from_bytes_legacy(data)

    @classmethod
    def _from_bytes_v1(cls, data: bytes) -> "StringTable":
        offset = 0
        version, offset = _decode_varint(data, offset)
        if version != _STRING_TABLE_VERSION:
            raise ValueError("unsupported string table version")
        count, offset = _decode_varint(data, offset)
        metadata: List[Tuple[int, int, int, int, int]] = []
        for _ in range(count):
            prefix, offset = _decode_varint(data, offset)
            suffix_len, offset = _decode_varint(data, offset)
            frequency, offset = _decode_varint(data, offset)
            type_id, offset = _decode_varint(data, offset)
            bucket, offset = _decode_varint(data, offset)
            metadata.append((prefix, suffix_len, frequency, type_id, bucket))

        type_streams, offset = _decode_varint(data, offset)
        backend = RANSBackend()
        grouped_suffix_bytes: Dict[int, List[int]] = {}
        for _ in range(type_streams):
            type_id, offset = _decode_varint(data, offset)
            byte_len, offset = _decode_varint(data, offset)
            model_length, offset = _decode_varint(data, offset)
            model_blob = data[offset : offset + model_length]
            offset += model_length
            model = json.loads(model_blob.decode("utf-8")) if model_blob else {"precision_bits": 12, "frequencies": []}
            compressed_len, offset = _decode_varint(data, offset)
            compressed = data[offset : offset + compressed_len]
            offset += compressed_len
            grouped_suffix_bytes[type_id] = backend.decode(compressed, model, byte_len) if byte_len else []

        entries: List[StringTableEntry] = []
        previous = ""
        positions: Dict[int, int] = {type_id: 0 for type_id in grouped_suffix_bytes}
        for prefix, suffix_len, frequency, type_id, bucket in metadata:
            stream = grouped_suffix_bytes.get(type_id, [])
            position = positions.get(type_id, 0)
            end = position + suffix_len
            if end > len(stream):
                raise ValueError("suffix stream truncated for type")
            suffix_bytes = bytes(stream[position:end])
            positions[type_id] = end
            suffix = suffix_bytes.decode("utf-8")
            value = previous[:prefix] + suffix
            entries.append(
                StringTableEntry(
                    value=value,
                    frequency=frequency,
                    prefix_length=prefix,
                    suffix=suffix,
                    type_id=type_id,
                    length_bucket=bucket,
                )
            )
            previous = value
        return cls(entries)

    @classmethod
    def _from_bytes_legacy(cls, data: bytes) -> "StringTable":
        offset = 0
        count, offset = _decode_varint(data, offset)
        entries: List[StringTableEntry] = []
        previous = ""
        for _ in range(count):
            prefix, offset = _decode_varint(data, offset)
            length, offset = _decode_varint(data, offset)
            end = offset + length
            suffix = data[offset:end].decode("utf-8")
            offset = end
            frequency, offset = _decode_varint(data, offset)
            value = previous[:prefix] + suffix
            entries.append(
                StringTableEntry(
                    value=value,
                    frequency=frequency,
                    prefix_length=prefix,
                    suffix=suffix,
                    type_id=_classify_string(value),
                    length_bucket=_length_bucket(value),
                )
            )
            previous = value
        return cls(entries)

    # ------------------------------------------------------------------
    # Payload serialisation helpers

    def encode_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return {_SENTINEL_KEY: self.index_for(value)}
        if isinstance(value, list):
            return [self.encode_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self.encode_value(item) for key, item in value.items()}
        return value

    def decode_value(self, value: Any) -> Any:
        if isinstance(value, dict) and set(value.keys()) == {_SENTINEL_KEY}:
            index = value[_SENTINEL_KEY]
            if not isinstance(index, int):
                raise ValueError("string reference index must be an integer")
            return self.string_for_index(index)
        if isinstance(value, list):
            return [self.decode_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self.decode_value(item) for key, item in value.items()}
        return value

    def encode_payload(self, payload: Any) -> Dict[str, Any]:
        if not hasattr(payload, "type") or not hasattr(payload, "value"):
            raise TypeError("payload objects must expose 'type' and 'value' attributes")
        return {"type": payload.type, "value": self.encode_value(payload.value)}

    def decode_payload(self, data: Dict[str, Any]) -> Any:
        payload_type = data.get("type")
        if not isinstance(payload_type, str):
            raise ValueError("payload type must be a string")
        return {
            "type": payload_type,
            "value": self.decode_value(data.get("value")),
        }


__all__ = ["StringTable", "StringTableEntry"]
