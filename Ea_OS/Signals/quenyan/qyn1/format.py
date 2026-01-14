"""Binary framing helpers for QYN-1 package transport."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import FrozenSet, Iterable, Iterator, Sequence, Tuple

from .versioning import Version, parse_any_version

WRAPPER_MAGIC = b"QYN1"
PAYLOAD_MAGIC = b"MCS\0"
WRAPPER_FLAG_ENCRYPTED = 0x0001
WRAPPER_FLAG_METADATA_AUTHENTICATED = 0x0002
PAYLOAD_FLAG_CANONICAL_SECTIONS = 0x0001

ENVELOPE_HEADER_STRUCT = struct.Struct(">4sBBHI")
SECTION_HEADER_STRUCT = struct.Struct("<HHI")
ENVELOPE_HEADER_SIZE = ENVELOPE_HEADER_STRUCT.size
SECTION_HEADER_SIZE = SECTION_HEADER_STRUCT.size

_FRAME_HEADER = struct.Struct(">4sBBHII")
_CRC_STRUCT = struct.Struct(">I")


class FrameFormatError(ValueError):
    """Raised when a frame fails validation during parsing."""


FormatError = FrameFormatError


class HeaderFormatError(FrameFormatError):
    """Raised when an envelope header fails validation."""

_FEATURE_BITS = {
    "compression:optimisation": 0,
    "compression:extras": 1,
    "payload:source-map": 2,
    "compression:fse": 3,
}


def _pack_version(version: Version) -> Tuple[int, int, int]:
    return version.major, version.minor, version.patch


def _decode_version(major: int, minor: int, patch: int) -> Version:
    return Version(major, minor, patch)


def _encode_feature_bits(features: Iterable[str], extra_bits: int = 0) -> int:
    bits = extra_bits
    for feature in features:
        try:
            index = _FEATURE_BITS[feature]
        except KeyError as exc:  # pragma: no cover - defensive
            raise FrameFormatError(f"unknown feature '{feature}'") from exc
        bits |= 1 << index
    return bits


def _decode_feature_bits(bits: int) -> Tuple[FrozenSet[str], FrozenSet[int]]:
    names = {name for name, index in _FEATURE_BITS.items() if bits & (1 << index)}
    unknown_indices = {
        index
        for index in range(0, 32)
        if bits & (1 << index) and index not in _FEATURE_BITS.values()
    }
    return frozenset(names), frozenset(unknown_indices)


@dataclass(frozen=True)
class EnvelopeHeader:
    """Parsed envelope header for wrapper and payload containers."""

    magic: bytes
    version: Version
    length: int

    @classmethod
    def parse(cls, data: bytes, *, expected_magic: bytes) -> Tuple["EnvelopeHeader", bytes]:
        if len(data) < ENVELOPE_HEADER_SIZE:
            raise HeaderFormatError("data too small to contain an envelope header")
        magic, major, minor, patch, length = ENVELOPE_HEADER_STRUCT.unpack_from(data, 0)
        if magic != expected_magic:
            raise HeaderFormatError(
                f"unexpected header magic {magic!r} (expected {expected_magic!r})"
            )
        version = _decode_version(major, minor, patch)
        remainder = data[ENVELOPE_HEADER_SIZE:]
        return cls(magic=magic, version=version, length=length), remainder

    def encode(self) -> bytes:
        return ENVELOPE_HEADER_STRUCT.pack(
            self.magic, *(_pack_version(self.version)), self.length
        )

    def split_body(self, body: bytes) -> Tuple[bytes, bytes]:
        if self.length > len(body):
            raise HeaderFormatError("envelope body truncated according to header length")
        payload = body[: self.length]
        remainder = body[self.length :]
        return payload, remainder


@dataclass(frozen=True)
class WrapperHeader(EnvelopeHeader):
    """Wrapper envelope header."""

    @classmethod
    def parse(cls, data: bytes) -> Tuple["WrapperHeader", bytes]:
        header, remainder = EnvelopeHeader.parse(data, expected_magic=WRAPPER_MAGIC)
        return cls(header.magic, header.version, header.length), remainder


@dataclass(frozen=True)
class PayloadHeader(EnvelopeHeader):
    """Payload envelope header."""

    @classmethod
    def parse(cls, data: bytes) -> Tuple["PayloadHeader", bytes]:
        header, remainder = EnvelopeHeader.parse(data, expected_magic=PAYLOAD_MAGIC)
        return cls(header.magic, header.version, header.length), remainder


@dataclass(frozen=True)
class Frame:
    """Single binary envelope with length-prefixing and CRC validation."""

    magic: bytes
    version: Version
    feature_bits: int
    features: FrozenSet[str]
    unknown_feature_bits: FrozenSet[int]
    body: bytes


@dataclass(frozen=True)
class Section:
    """Versioned logical payload block embedded within a frame body."""

    identifier: int
    flags: int
    payload: bytes


@dataclass(frozen=True)
class SectionHeader:
    """Legacy section header compatibility shim."""

    sid: int
    flags: int
    length: int = 0
    checksum: int = 0


@dataclass(frozen=True)
class SectionRecord:
    """Wrapper used by legacy code paths when parsing sections."""

    header: SectionHeader
    payload: bytes


def write_frame(
    *,
    magic: bytes,
    version: Version,
    features: Iterable[str] | None = None,
    extra_feature_bits: int = 0,
    body: bytes,
) -> bytes:
    """Serialise a frame with the configured magic and feature flags."""

    if len(magic) != 4:
        raise FrameFormatError("frame magic must be exactly 4 bytes")
    feature_bits = _encode_feature_bits(features or (), extra_feature_bits)
    header = _FRAME_HEADER.pack(
        magic,
        *_pack_version(version),
        feature_bits,
        len(body),
    )
    crc = zlib.crc32(body) & 0xFFFFFFFF
    return header + body + _CRC_STRUCT.pack(crc)


def read_frame(data: bytes, *, expected_magic: bytes | None = None) -> Tuple[Frame, bytes]:
    """Parse the leading frame from *data* returning the frame and remainder."""

    if len(data) < _FRAME_HEADER.size + _CRC_STRUCT.size:
        raise FrameFormatError("data too small to contain a frame")
    magic, major, minor, patch, feature_bits, body_length = _FRAME_HEADER.unpack_from(
        data, 0
    )
    if expected_magic is not None and magic != expected_magic:
        raise HeaderFormatError(
            f"unexpected frame magic {magic!r} (expected {expected_magic!r})"
        )
    start = _FRAME_HEADER.size
    end = start + body_length
    crc_start = end
    crc_end = crc_start + _CRC_STRUCT.size
    if crc_end > len(data):
        raise FrameFormatError("frame truncated before CRC")
    body = data[start:end]
    (stored_crc,) = _CRC_STRUCT.unpack_from(data, crc_start)
    calculated_crc = zlib.crc32(body) & 0xFFFFFFFF
    if calculated_crc != stored_crc:
        raise FrameFormatError("frame CRC mismatch")
    version = _decode_version(major, minor, patch)
    features, unknown = _decode_feature_bits(feature_bits)
    frame = Frame(
        magic=magic,
        version=version,
        feature_bits=feature_bits,
        features=features,
        unknown_feature_bits=unknown,
        body=body,
    )
    remainder = data[crc_end:]
    return validate_frame(frame, expected_magic=expected_magic), remainder


def encode_sections(sections: Sequence[Section]) -> bytes:
    """Encode *sections* into a binary stream suitable for a payload body."""

    payloads = []
    for section in sections:
        if hasattr(section, "identifier"):
            identifier = section.identifier  # type: ignore[attr-defined]
            flags = section.flags  # type: ignore[attr-defined]
            payload = section.payload  # type: ignore[attr-defined]
        else:
            header = section.header  # type: ignore[attr-defined]
            identifier = header.sid
            flags = header.flags
            payload = section.payload  # type: ignore[attr-defined]
        payloads.append(
            SECTION_HEADER_STRUCT.pack(identifier, flags, len(payload)) + payload
        )
    return b"".join(payloads)


def decode_sections(buffer: bytes) -> Iterator[Section]:
    """Yield sections from the provided *buffer* without interpretation."""

    offset = 0
    length = len(buffer)
    while offset < length:
        if offset + SECTION_HEADER_STRUCT.size > length:
            raise FrameFormatError("truncated section header")
        identifier, flags, payload_length = SECTION_HEADER_STRUCT.unpack_from(buffer, offset)
        offset += SECTION_HEADER_STRUCT.size
        end = offset + payload_length
        if end > length:
            raise FrameFormatError("truncated section payload")
        payload = buffer[offset:end]
        offset = end
        yield Section(identifier=identifier, flags=flags, payload=payload)


def validate_frame(frame: Frame, *, expected_magic: bytes | None = None) -> Frame:
    """Validate the structural invariants for a parsed frame."""

    if len(frame.magic) != 4:
        raise HeaderFormatError("frame magic must be exactly 4 bytes")
    if expected_magic is not None and frame.magic != expected_magic:
        raise HeaderFormatError(
            f"unexpected frame magic {frame.magic!r} (expected {expected_magic!r})"
        )
    if frame.feature_bits < 0:
        raise FrameFormatError("frame feature bits cannot be negative")
    if not isinstance(frame.body, (bytes, bytearray)):
        raise FrameFormatError("frame body must be bytes-like")
    return frame


def validate_sections(sections: Iterable[Section]) -> Tuple[Section, ...]:
    """Validate section headers and payloads before downstream parsing."""

    validated = []
    for section in sections:
        if not 0 <= section.identifier <= 0xFFFF:
            raise FrameFormatError("section identifier must fit in 16 bits")
        if not 0 <= section.flags <= 0xFFFF:
            raise FrameFormatError("section flags must fit in 16 bits")
        if not isinstance(section.payload, (bytes, bytearray)):
            raise FrameFormatError("section payload must be bytes-like")
        validated.append(section)
    return tuple(validated)


def parse_version(value: str) -> Version:
    """Parse a textual version inside framing metadata."""

    return parse_any_version(value)

# Compatibility aliases
encode_frame = write_frame
decode_frame = read_frame


__all__ = [
    "WRAPPER_MAGIC",
    "PAYLOAD_MAGIC",
    "WRAPPER_FLAG_ENCRYPTED",
    "WRAPPER_FLAG_METADATA_AUTHENTICATED",
    "PAYLOAD_FLAG_CANONICAL_SECTIONS",
    "ENVELOPE_HEADER_STRUCT",
    "SECTION_HEADER_STRUCT",
    "ENVELOPE_HEADER_SIZE",
    "SECTION_HEADER_SIZE",
    "EnvelopeHeader",
    "WrapperHeader",
    "PayloadHeader",
    "Frame",
    "Section",
    "HeaderFormatError",
    "FrameFormatError",
    "FormatError",
    "SectionHeader",
    "SectionRecord",
    "decode_sections",
    "validate_frame",
    "validate_sections",
    "parse_version",
    "encode_frame",
    "decode_frame",
    "read_frame",
    "write_frame",
    "encode_sections",
]
