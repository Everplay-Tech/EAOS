"""Reference MCS encoder/decoder aligned with the framed package format."""

from __future__ import annotations

import base64
import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from qyn1.crypto import (
    EncryptionResult,
    decrypt,
    derive_key_from_passphrase,
    _chacha20_poly1305_encrypt,
)
from qyn1.format import (
    PAYLOAD_MAGIC,
    WRAPPER_MAGIC,
    decode_sections,
    read_frame,
    write_frame,
)

FEATURE_BITS = {
    "compression:optimisation": 0,
    "compression:extras": 1,
    "payload:source-map": 2,
    "compression:fse": 3,
}

SECTION_PAYLOAD_IDENTIFIERS = 0x0101
SECTION_PAYLOAD_STRINGS = 0x0102
SECTION_PAYLOAD_INTEGERS = 0x0103
SECTION_PAYLOAD_COUNTS = 0x0104
SECTION_PAYLOAD_FLAGS = 0x0105

CANONICAL_VERSIONS: Dict[str, str] = json.loads(
    (Path(__file__).resolve().parent.parent / "canonical_versions.json").read_text()
)


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "Version":
        parts = value.strip().split(".")
        if len(parts) == 2:
            major, minor = parts
            patch = 0
        elif len(parts) == 3:
            major, minor, patch = parts
        else:
            raise ValueError(f"invalid semantic version '{value}'")
        return cls(int(major), int(minor), int(patch))

    @property
    def text(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def _canonical_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _metadata_aad(metadata: Dict[str, Any]) -> bytes:
    return b"QYN1-METADATA-v1:" + _canonical_json(metadata).encode("utf-8")


def _write_utf8(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 0xFFFF:
        raise ValueError("string too long for u16 length prefix")
    return struct.pack("<H", len(encoded)) + encoded


def _read_utf8(buffer: bytes, offset: int) -> Tuple[str, int]:
    if offset + 2 > len(buffer):
        raise ValueError("buffer truncated while reading string length")
    (length,) = struct.unpack_from("<H", buffer, offset)
    offset += 2
    end = offset + length
    if end > len(buffer):
        raise ValueError("buffer truncated while reading string payload")
    return buffer[offset:end].decode("utf-8"), end


def _write_length_prefixed(data: bytes) -> bytes:
    return struct.pack("<I", len(data)) + data


def _read_length_prefixed(buffer: bytes) -> bytes:
    if len(buffer) < 4:
        raise ValueError("length-prefixed buffer too small")
    (length,) = struct.unpack_from("<I", buffer, 0)
    payload = buffer[4 : 4 + length]
    if len(payload) != length:
        raise ValueError("length-prefixed buffer truncated")
    return payload


def _write_section(sid: int, flags: int, payload: bytes) -> bytes:
    return struct.pack("<HHI", sid, flags, len(payload)) + payload


def _encode_feature_bits(features: Iterable[str]) -> int:
    bits = 0
    for name in features:
        index = FEATURE_BITS.get(name)
        if index is None:
            raise ValueError(f"unknown feature '{name}'")
        bits |= 1 << index
    return bits


def _decode_feature_bits(bits: int) -> set[str]:
    names = {name for name, index in FEATURE_BITS.items() if bits & (1 << index)}
    unknown = bits & ~sum(1 << index for index in FEATURE_BITS.values())
    if unknown:
        raise ValueError(f"frame advertises unknown feature bits 0x{unknown:08x}")
    return names


def decode(data: bytes, passphrase: str) -> Dict[str, Any]:
    frame, remainder = read_frame(data, expected_magic=WRAPPER_MAGIC)
    if remainder:
        raise ValueError("unexpected trailing data after wrapper frame")
    wrapper = json.loads(frame.body.decode("utf-8"))
    advertised_features = set(wrapper.get("payload_features", []))
    if advertised_features and advertised_features != set(frame.features):
        raise ValueError("wrapper feature bitset mismatch")

    encrypted = EncryptionResult(
        nonce=base64.b64decode(wrapper["nonce"]),
        salt=base64.b64decode(wrapper["salt"]),
        hkdf_salt=base64.b64decode(wrapper.get("hkdf_salt", wrapper["salt"])),
        ciphertext=base64.b64decode(wrapper["ciphertext"]),
        tag=base64.b64decode(wrapper["tag"]),
        version=int(wrapper.get("encryption_version", 1)),
        aead=str(wrapper.get("aead", "chacha20poly1305")),
        kdf=str(wrapper.get("kdf", "pbkdf2")),
        kdf_parameters={
            key: int(value) for key, value in dict(wrapper.get("kdf_parameters", {})).items()
        },
    )
    metadata = wrapper["metadata"]
    payload_bytes = decrypt(encrypted, passphrase, _metadata_aad(metadata))

    payload_frame, payload_remainder = read_frame(
        payload_bytes, expected_magic=PAYLOAD_MAGIC
    )
    if payload_remainder:
        raise ValueError("unexpected trailing data after payload frame")
    if set(payload_frame.features) != set(frame.features):
        raise ValueError("payload feature set mismatch with wrapper")

    sections = {section.identifier: section for section in decode_sections(payload_frame.body)}

    stream = sections[0x0001]
    offset = 0
    dictionary_version, offset = _read_utf8(stream.payload, offset)
    encoder_version, offset = _read_utf8(stream.payload, offset)
    source_language, offset = _read_utf8(stream.payload, offset)
    source_language_version, offset = _read_utf8(stream.payload, offset)
    (symbol_count,) = struct.unpack_from("<I", stream.payload, offset)
    offset += 4
    _hash_type = stream.payload[offset]
    offset += 1
    source_hash_bytes = stream.payload[offset : offset + 32]
    source_hash = source_hash_bytes.hex() if source_hash_bytes.strip(b"\x00") else ""

    compression = sections[0x0002]
    offset = 0
    backend, offset = _read_utf8(compression.payload, offset)
    (comp_symbol_count,) = struct.unpack_from("<I", compression.payload, offset)
    offset += 4
    model_json = _read_length_prefixed(compression.payload[offset:])
    offset += 4 + len(model_json)
    extras_json = _read_length_prefixed(compression.payload[offset:])
    extras = json.loads(extras_json.decode("utf-8")) if extras_json else {}
    model = json.loads(model_json.decode("utf-8")) if model_json else {}

    tokens_blob = _read_length_prefixed(sections[0x0003].payload)
    string_table_blob = _read_length_prefixed(sections[0x0004].payload)

    payload_record = json.loads(
        _read_length_prefixed(sections[0x0005].payload).decode("utf-8")
    )

    payload_channels: Dict[str, Any] = {}
    channel_map = {
        SECTION_PAYLOAD_IDENTIFIERS: "identifiers",
        SECTION_PAYLOAD_STRINGS: "strings",
        SECTION_PAYLOAD_INTEGERS: "integers",
        SECTION_PAYLOAD_COUNTS: "counts",
        SECTION_PAYLOAD_FLAGS: "flags",
    }
    for sid, name in channel_map.items():
        section = sections.get(sid)
        if section is None:
            continue
        payload_channels[name] = json.loads(
            _read_length_prefixed(section.payload).decode("utf-8")
        )

    source_map_blob = None
    if 0x0006 in sections:
        source_map_blob = base64.b64encode(
            _read_length_prefixed(sections[0x0006].payload)
        ).decode("ascii")

    metadata_inner = json.loads(
        _read_length_prefixed(sections[0x0007].payload).decode("utf-8")
    )

    descriptor = {
        "wrapper_version": frame.version.text,
        "payload_version": payload_frame.version.text,
        "payload_features": sorted(payload_frame.features),
        "metadata": metadata_inner,
        "salt": wrapper["salt"],
        "nonce": wrapper["nonce"],
        "sections": {
            "stream_header": {
                "dictionary_version": dictionary_version,
                "encoder_version": encoder_version,
                "source_language": source_language,
                "source_language_version": source_language_version,
                "symbol_count": int(symbol_count),
                "source_hash": source_hash,
                "has_source_map": bool(stream.flags & 0x0001),
            },
            "compression": {
                "backend": backend,
                "symbol_count": int(comp_symbol_count),
                "model": model,
                "extras": extras,
            },
            "tokens": base64.b64encode(tokens_blob).decode("ascii"),
            "string_table": base64.b64encode(string_table_blob).decode("ascii"),
            "payloads": payload_record,
        },
    }

    if payload_channels:
        descriptor["sections"]["payload_channels"] = payload_channels
    if source_map_blob is not None:
        descriptor["sections"]["source_map"] = source_map_blob
    return descriptor


def encode(descriptor: Dict[str, Any], passphrase: str) -> bytes:
    wrapper_version_text = descriptor.get("wrapper_version") or CANONICAL_VERSIONS["wrapper_version"]
    payload_version_text = descriptor.get("payload_version") or CANONICAL_VERSIONS["payload_version"]
    wrapper_version = Version.parse(wrapper_version_text)
    payload_version = Version.parse(payload_version_text)
    metadata = descriptor.get("metadata", {})
    sections = descriptor["sections"]

    stream = sections["stream_header"]
    dictionary_version = stream.get("dictionary_version") or CANONICAL_VERSIONS["dictionary_version"]
    stream_payload = bytearray()
    stream_payload.extend(_write_utf8(dictionary_version))
    stream_payload.extend(_write_utf8(stream.get("encoder_version", "")))
    stream_payload.extend(_write_utf8(stream.get("source_language", "")))
    stream_payload.extend(_write_utf8(stream.get("source_language_version", "")))
    stream_payload.extend(struct.pack("<I", int(stream.get("symbol_count", 0))))
    stream_payload.append(0)
    source_hash = stream.get("source_hash", "")
    if source_hash:
        stream_payload.extend(bytes.fromhex(source_hash))
    else:
        stream_payload.extend(b"\x00" * 32)
    stream_section = _write_section(
        0x0001, 0x0001 if stream.get("has_source_map") else 0, bytes(stream_payload)
    )

    compression = sections["compression"]
    compression_payload = bytearray()
    compression_payload.extend(_write_utf8(compression["backend"]))
    compression_payload.extend(struct.pack("<I", int(compression["symbol_count"])))
    model_json = _canonical_json(compression["model"]).encode("utf-8")
    compression_payload.extend(_write_length_prefixed(model_json))
    extras = compression.get("extras") or {}
    extras_blob = _canonical_json(extras).encode("utf-8") if extras else b""
    compression_payload.extend(_write_length_prefixed(extras_blob))
    compression_section = _write_section(0x0002, 0, bytes(compression_payload))

    tokens_blob = base64.b64decode(sections["tokens"])
    tokens_section = _write_section(0x0003, 0, _write_length_prefixed(tokens_blob))

    string_table_blob = base64.b64decode(sections["string_table"])
    string_table_section = _write_section(
        0x0004, 0, _write_length_prefixed(string_table_blob)
    )

    payload_body = sections.get("payloads", {})
    payload_json = _canonical_json(payload_body).encode("utf-8")
    payload_section = _write_section(0x0005, 0, _write_length_prefixed(payload_json))

    channel_sections = []
    channel_map = {
        "identifiers": SECTION_PAYLOAD_IDENTIFIERS,
        "strings": SECTION_PAYLOAD_STRINGS,
        "integers": SECTION_PAYLOAD_INTEGERS,
        "counts": SECTION_PAYLOAD_COUNTS,
        "flags": SECTION_PAYLOAD_FLAGS,
    }
    for name, sid in channel_map.items():
        channel_payload = sections.get("payload_channels", {}).get(name)
        if channel_payload is None:
            continue
        payload = _canonical_json(channel_payload).encode("utf-8")
        channel_sections.append(_write_section(sid, 0, _write_length_prefixed(payload)))

    source_map_section = b""
    if sections.get("source_map"):
        source_map_blob = base64.b64decode(sections["source_map"])
        source_map_section = _write_section(
            0x0006, 0, _write_length_prefixed(source_map_blob)
        )

    metadata_blob = _canonical_json(metadata).encode("utf-8")
    metadata_section = _write_section(0x0007, 0, _write_length_prefixed(metadata_blob))

    payload_body_bytes = b"".join(
        [
            stream_section,
            compression_section,
            tokens_section,
            string_table_section,
            payload_section,
            *channel_sections,
            source_map_section,
            metadata_section,
        ]
    )

    features = set(descriptor.get("payload_features") or [])
    if not features:
        if extras:
            features.add("compression:extras")
            if "optimisation" in extras:
                features.add("compression:optimisation")
        if compression["backend"] == "fse":
            features.add("compression:fse")
        if source_map_section:
            features.add("payload:source-map")
    payload_frame = write_frame(
        magic=PAYLOAD_MAGIC,
        version=payload_version,
        features=features,
        body=payload_body_bytes,
    )

    salt = (
        base64.b64decode(descriptor["salt"])
        if "salt" in descriptor
        else os.urandom(16)
    )
    nonce = (
        base64.b64decode(descriptor["nonce"])
        if "nonce" in descriptor
        else os.urandom(12)
    )
    key = derive_key_from_passphrase(passphrase, salt)
    ciphertext, tag = _chacha20_poly1305_encrypt(
        key, nonce, payload_frame, _metadata_aad(metadata)
    )

    wrapper_body = {
        "version": wrapper_version.text,
        "payload_version": payload_version.text,
        "payload_features": sorted(features),
        "metadata": metadata,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
    }
    wrapper_bytes = _canonical_json(wrapper_body).encode("utf-8")
    return write_frame(
        magic=WRAPPER_MAGIC,
        version=wrapper_version,
        features=features,
        body=wrapper_bytes,
    )
