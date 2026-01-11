"""Packaging helpers for QYN-1 streams."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .compression import (
    CompressionBackend,
    OptionalBackendUnavailable,
    RANSBackend,
    RANSCodec,
    RANSTable,
    get_backend,
)
from .compression_config import CompressionConfig, get_compression_config
from .crypto import EncryptionResult, decrypt, encrypt
from .dictionary import ensure_dictionary_supported, load_dictionary
from .encoder import EncodedStream
from .format import (
    ENVELOPE_HEADER_SIZE,
    HeaderFormatError,
    PayloadHeader,
    Section,
    SectionHeader,
    SectionRecord,
    WrapperHeader,
    FormatError,
    FrameFormatError,
    WRAPPER_FLAG_ENCRYPTED,
    WRAPPER_FLAG_METADATA_AUTHENTICATED,
    WRAPPER_MAGIC,
    PAYLOAD_FLAG_CANONICAL_SECTIONS,
    PAYLOAD_MAGIC,
    decode_frame,
    decode_sections,
    encode_frame,
    encode_sections,
    read_frame,
    validate_frame,
    validate_sections,
)
from .models import GlobalModelRegistry, ModelMode, build_sparse_overrides, resolve_model_mode
from .payloads import Payload, PayloadChannels
from .resource_limits import ResourceBudget, ResourceBudgetExceeded
from .source_map import SourceMap
from .string_table import StringTable
from .token_optimisation import TokenOptimisationPlan, build_frequency_plan
from .versioning import (
    CURRENT_PACKAGE_VERSION,
    MINIMUM_SUPPORTED_PACKAGE_VERSION,
    Version,
    ensure_supported,
    negotiate_version,
    parse_any_version,
)

DEFAULT_CHUNK_SIZE = 65536
ENCODING_VERSION = "qyn1.1-multi-channel"

PAYLOAD_CHANNEL_TOKEN = 0x01
PAYLOAD_CHANNEL_IDENTIFIER = 0x02
PAYLOAD_CHANNEL_STRING = 0x04
PAYLOAD_CHANNEL_INTEGER = 0x08
PAYLOAD_CHANNEL_COUNT = 0x10
PAYLOAD_CHANNEL_FLAG = 0x20

SECTION_PAYLOAD_IDENTIFIERS = 0x0101
SECTION_PAYLOAD_STRINGS = 0x0102
SECTION_PAYLOAD_INTEGERS = 0x0103
SECTION_PAYLOAD_COUNTS = 0x0104
SECTION_PAYLOAD_FLAGS = 0x0105

SECTION_STREAM_HEADER = 0x0001
SECTION_COMPRESSION = 0x0002
SECTION_TOKENS = 0x0003
SECTION_STRING_TABLE = 0x0004
SECTION_PAYLOADS = 0x0005
SECTION_SOURCE_MAP = 0x0006
SECTION_METADATA = 0x0007

PACKAGE_VERSION = CURRENT_PACKAGE_VERSION.text
LEGACY_ASSOCIATED_DATA = b"QYN1-PACKAGE-v1"


class PackageBytes(bytes):
    """Bytes subclass that exposes wrapper JSON when decoded as UTF-8."""

    def decode(self, encoding: str = "utf-8", errors: str = "strict"):  # type: ignore[override]
        normalised = encoding.replace("_", "-").lower()
        if normalised == "utf-8" and len(self) >= ENVELOPE_HEADER_SIZE and self.startswith(WRAPPER_MAGIC):
            header, _ = WrapperHeader.parse(self)
            body, _ = header.split_body(self[ENVELOPE_HEADER_SIZE :])
            return bytes(body).decode(encoding, errors)
        return super().decode(encoding, errors)


def _parse_kdf_parameters(wrapper: Dict[str, Any]) -> Dict[str, int]:
    raw_params = wrapper.get("kdf_parameters", {})
    if raw_params is None:
        return {}
    if not isinstance(raw_params, dict):
        raise ValueError("kdf_parameters must be an object when provided")
    parsed: Dict[str, int] = {}
    for key, value in raw_params.items():
        parsed[key] = int(value)
    return parsed


def decompress_internal(
    backend: CompressionBackend,
    data: bytes,
    model: Dict[str, Any],
    symbol_count: int,
    *,
    budget: ResourceBudget,
) -> List[int]:
    """Decompress tokens enforcing the provided resource budget."""

    budget.ensure_symbols(symbol_count)
    budget.ensure_compressed(len(data))
    budget.ensure_model(model)
    return backend.decode(data, model, symbol_count)


def _canonicalise_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _write_utf8(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 0xFFFF:
        raise ValueError("string value exceeds 65535 bytes")
    return struct.pack("<H", len(encoded)) + encoded


def _read_utf8(buffer: bytes, offset: int) -> Tuple[str, int]:
    if offset + 2 > len(buffer):
        raise ValueError("unexpected end of buffer while reading string length")
    (length,) = struct.unpack_from("<H", buffer, offset)
    offset += 2
    end = offset + length
    if end > len(buffer):
        raise ValueError("unexpected end of buffer while reading string payload")
    return buffer[offset:end].decode("utf-8"), end


def _write_u32_le(value: int) -> bytes:
    return struct.pack("<I", value)


def _read_u32_from(buffer: bytes, offset: int) -> Tuple[int, int]:
    if offset + 4 > len(buffer):
        raise ValueError("buffer truncated while reading u32")
    (value,) = struct.unpack_from("<I", buffer, offset)
    return value, offset + 4


def _decode_length_prefixed_bytes(payload: bytes) -> bytes:
    if len(payload) < 4:
        raise ValueError("length-prefixed payload too small")
    (length,) = struct.unpack_from("<I", payload, 0)
    data = payload[4 : 4 + length]
    if len(data) != length:
        raise ValueError("length-prefixed payload truncated")
    if len(payload) != 4 + length:
        raise ValueError("unexpected data after length-prefixed payload")
    return data
def _make_section(sid: int, flags: int, payload: bytes) -> SectionRecord:
    header = SectionHeader(sid, flags, len(payload), 0)
    return SectionRecord(header, payload)


def _join_sections(sections: Iterable[SectionRecord]) -> bytes:
    return encode_sections(sections)


def _decode_length_prefixed_json(payload: bytes) -> Dict[str, Any]:
    data = _decode_length_prefixed_bytes(payload)
    return json.loads(data.decode("utf-8"))


def _materialise_payloads(payload_record: Dict[str, Any], string_table: StringTable) -> List[Payload]:
    channels_data = payload_record.get("channels")
    if channels_data is not None:
        channels = PayloadChannels.from_serializable(channels_data, string_table)
        return channels.to_payloads(string_table)
    payloads = payload_record.get("payloads")
    if payloads is None:
        payloads = payload_record.get("legacy_payloads")
    if not isinstance(payloads, list):
        raise ValueError("payload section must contain payload entries")
    decoded_payloads = []
    for entry in payloads:
        decoded = string_table.decode_payload(entry)
        decoded_payloads.append(Payload(decoded["type"], decoded["value"]))
    return _normalise_payloads(decoded_payloads)


def _decode_source_hash(value: str) -> bytes:
    if not value:
        return b"\x00" * 32
    data = bytes.fromhex(value)
    if len(data) != 32:
        raise ValueError("source hash must be a 32-byte SHA-256 digest")
    return data


def _digest_model(model: Dict[str, Any]) -> str:
    canonical = _canonicalise_json(model)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Data classes


@dataclass
class PackageMetadata:
    package_version: str
    dictionary_version: str
    encoder_version: str
    source_language: str
    source_language_version: str
    source_hash: str
    compression_backend: str
    compression_model_digest: str
    symbol_count: int
    timestamp: Optional[str] = None
    author: Optional[str] = None
    license: Optional[str] = None
    key_provider: Optional[str] = None
    key_id: Optional[str] = None
    key_version: Optional[str] = None
    rotation_due: Optional[str] = None
    audit_trail: Optional[List[Dict[str, Any]]] = None
    provenance: Optional[Dict[str, Any]] = None
    integrity_signature: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "package_version": self.package_version,
            "dictionary_version": self.dictionary_version,
            "encoder_version": self.encoder_version,
            "source_language": self.source_language,
            "source_language_version": self.source_language_version,
            "source_hash": self.source_hash,
            "compression_backend": self.compression_backend,
            "compression_model_digest": self.compression_model_digest,
            "symbol_count": self.symbol_count,
        }
        if self.timestamp is not None:
            data["timestamp"] = self.timestamp
        if self.author is not None:
            data["author"] = self.author
        if self.license is not None:
            data["license"] = self.license
        if self.key_provider is not None:
            data["key_provider"] = self.key_provider
        if self.key_id is not None:
            data["key_id"] = self.key_id
        if self.key_version is not None:
            data["key_version"] = self.key_version
        if self.rotation_due is not None:
            data["rotation_due"] = self.rotation_due
        if self.audit_trail is not None:
            data["audit_trail"] = self.audit_trail
        if self.provenance is not None:
            data["provenance"] = self.provenance
        if self.integrity_signature is not None:
            data["integrity_signature"] = self.integrity_signature
        return data

    def to_associated_data(self) -> bytes:
        return b"QYN1-METADATA-v1:" + _canonicalise_json(self.to_dict()).encode("utf-8")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PackageMetadata":
        required = {
            "package_version",
            "dictionary_version",
            "encoder_version",
            "source_language",
            "source_language_version",
            "source_hash",
            "compression_backend",
            "compression_model_digest",
            "symbol_count",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError(f"metadata is missing required fields: {', '.join(missing)}")
        return cls(
            package_version=str(data["package_version"]),
            dictionary_version=str(data["dictionary_version"]),
            encoder_version=str(data["encoder_version"]),
            source_language=str(data["source_language"]),
            source_language_version=str(data["source_language_version"]),
            source_hash=str(data["source_hash"]),
            compression_backend=str(data["compression_backend"]),
            compression_model_digest=str(data["compression_model_digest"]),
            symbol_count=int(data["symbol_count"]),
            timestamp=str(data["timestamp"]) if "timestamp" in data else None,
            author=str(data["author"]) if "author" in data else None,
            license=str(data["license"]) if "license" in data else None,
            key_provider=str(data["key_provider"]) if "key_provider" in data else None,
            key_id=str(data["key_id"]) if "key_id" in data else None,
            key_version=str(data["key_version"]) if "key_version" in data else None,
            rotation_due=str(data["rotation_due"]) if "rotation_due" in data else None,
            audit_trail=list(data["audit_trail"]) if "audit_trail" in data else None,
            provenance=dict(data["provenance"]) if "provenance" in data else None,
            integrity_signature=dict(data["integrity_signature"]) if "integrity_signature" in data else None,
        )


@dataclass
class QYNPackage:
    dictionary_version: str
    encoder_version: str
    compression_backend: str
    compression_model: Dict[str, Any]
    compressed_tokens: bytes
    payloads: List[Payload]
    symbol_count: int
    string_table_bytes: bytes
    encoded_payloads: List[Dict[str, Any]]
    metadata: PackageMetadata
    source_map_bytes: Optional[bytes] = None
    compression_extras: Optional[Dict[str, Any]] = None
    payload_channels: "PayloadChannels | None" = None

    def to_json(self) -> Dict[str, Any]:
        compression_section: Dict[str, Any] = {
            "backend": self.compression_backend,
            "model": self.compression_model,
            "symbol_count": self.symbol_count,
        }
        if self.compression_extras:
            compression_section.update(self.compression_extras)
        data = {
            "version": CURRENT_PACKAGE_VERSION.text,
            "dictionary_version": self.dictionary_version,
            "encoder_version": self.encoder_version,
            "compression": compression_section,
            "compressed_tokens": base64.b64encode(self.compressed_tokens).decode("ascii"),
            "string_table": base64.b64encode(self.string_table_bytes).decode("ascii"),
            "payloads": self.encoded_payloads,
            "metadata": self.metadata.to_dict(),
        }
        if self.source_map_bytes is not None:
            data["source_map"] = base64.b64encode(self.source_map_bytes).decode("ascii")
        return data

    def to_bytes(self, passphrase: str, *, prefer_versions: Iterable[str] | None = None) -> bytes:
        return write_package(self, passphrase, prefer_versions=prefer_versions)
    def to_bytes(self, passphrase: str) -> bytes:
        return write_package(self, passphrase)


# ---------------------------------------------------------------------------
# Public helpers


def encode_package(
    stream: EncodedStream,
    backend_name: str = "rans",
    *,
    compression: CompressionConfig | None = None,
    model_mode: ModelMode | str | None = None,
    string_table: StringTable | None = None,
    token_plan: TokenOptimisationPlan | None = None,
    author: Optional[str] = None,
    license: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> QYNPackage:
    ensure_dictionary_supported(stream.dictionary_version)
    base_config = get_compression_config(None)
    config = compression or base_config
    if compression is not None:
        backend_name = config.backend
    backend_kwargs: Dict[str, Any] = {}
    if compression is not None:
        backend_kwargs = config.backend_kwargs()
    elif backend_name == config.backend:
        backend_kwargs = config.backend_kwargs()
    backend = get_backend(backend_name, **backend_kwargs)
    active_model_mode = resolve_model_mode(model_mode or getattr(config, "model_mode", "adaptive"))
    if active_model_mode is not ModelMode.ADAPTIVE and backend.name not in {"rans", "chunked-rans"}:
        # Non-rANS backends currently rely on fully adaptive counts.
        active_model_mode = ModelMode.ADAPTIVE
    plan = token_plan
    if plan is None and config.token_optimisation == "local":
        plan = build_frequency_plan(stream.tokens)
    optimisation_metadata: Optional[Dict[str, Any]] = None
    if plan is not None:
        optimised_tokens = plan.apply(stream.tokens)
        alphabet_size = plan.alphabet_size
        optimisation_metadata = plan.to_metadata()
    else:
        optimised_tokens = list(stream.tokens)
        alphabet_size = len(stream.dictionary)
    model: Dict[str, Any]
    if active_model_mode is ModelMode.STATIC:
        global_model = GlobalModelRegistry.load()
        frequencies = list(global_model.frequencies)
        if len(frequencies) < alphabet_size:
            frequencies.extend([1] * (alphabet_size - len(frequencies)))
        model = {
            "mode": ModelMode.STATIC.value,
            "model_id": global_model.model_id,
            "precision_bits": global_model.precision_bits,
            "alphabet_size": alphabet_size,
        }
    elif active_model_mode is ModelMode.HYBRID:
        adaptive_model = backend.build_model(optimised_tokens, alphabet_size)
        global_model = GlobalModelRegistry.load()
        base_freq = list(global_model.frequencies)
        if len(base_freq) < alphabet_size:
            base_freq.extend([1] * (alphabet_size - len(base_freq)))
        overrides = build_sparse_overrides(adaptive_model.get("frequencies", []), base_freq)
        model = {
            "mode": ModelMode.HYBRID.value,
            "model_id": global_model.model_id,
            "precision_bits": int(adaptive_model.get("precision_bits", global_model.precision_bits)),
            "alphabet_size": alphabet_size,
            "overrides": overrides,
        }
    else:
        model = backend.build_model(optimised_tokens, alphabet_size)
    compressed = backend.encode(list(optimised_tokens), model)
    normalised_payloads = [_normalise_payload(payload) for payload in stream.payloads]
    if string_table is None:
        string_table = StringTable.build_from_payloads(normalised_payloads)
    encoded_payloads = [string_table.encode_payload(payload) for payload in normalised_payloads]
    # All payloads travel through channelised ANS sub-streams that use
    # distribution-aware priors (Zipf for identifiers, geometric/log buckets for
    # counts and numbers, Bernoulli for flags). The plain payload list remains
    # for observability and legacy tooling, but the encoded package relies on
    # the specialised channels rebuilt against the package string table to
    # guarantee stable indices and frequency models.
    payload_channels = PayloadChannels.build(normalised_payloads, string_table)
    payload_channels.apply_token_indices(stream.payload_channels.entries)
    payload_channels.token_keys = [
        stream.dictionary.entry_for_index(index).key for index in stream.tokens
    ]
    source_map_bytes: Optional[bytes] = None
    if stream.source_map is not None:
        source_map_bytes = stream.source_map.to_bytes()
    metadata = PackageMetadata(
        package_version=CURRENT_PACKAGE_VERSION.text,
        dictionary_version=stream.dictionary_version,
        encoder_version=stream.encoder_version,
        source_language=stream.source_language,
        source_language_version=stream.source_language_version,
        source_hash=stream.source_hash,
        compression_backend=backend.name,
        compression_model_digest=_digest_model(model),
        symbol_count=len(stream.tokens),
        timestamp=timestamp or stream.timestamp,
        author=author or stream.author,
        license=license or stream.license,
    )
    compression_extras: Dict[str, Any] = {}
    if compression is not None:
        compression_extras["mode"] = config.mode
        compression_extras["model_mode"] = active_model_mode.value
    if optimisation_metadata is not None:
        compression_extras["optimisation"] = optimisation_metadata
    if not compression_extras:
        compression_extras = None
    return QYNPackage(
        dictionary_version=stream.dictionary_version,
        encoder_version=stream.encoder_version,
        compression_backend=backend.name,
        compression_model=model,
        compressed_tokens=compressed,
        payloads=normalised_payloads,
        symbol_count=len(stream.tokens),
        string_table_bytes=string_table.to_bytes(),
        encoded_payloads=encoded_payloads,
        payload_channels=payload_channels,
        metadata=metadata,
        source_map_bytes=source_map_bytes,
        compression_extras=compression_extras,
    )


def write_package(
    package: QYNPackage,
    passphrase: str,
    *,
    prefer_versions: Iterable[str] | None = None,
    extra_features: Iterable[str] | None = None,
) -> bytes:
    payload_frame, payload_version, payload_features = _serialise_payload(
        package, prefer_versions, extra_features
    )
    metadata = package.metadata
    associated_data = metadata.to_associated_data()
    encrypted = encrypt(payload_frame, passphrase, associated_data)
    wrapper_body = {
        "version": CURRENT_PACKAGE_VERSION.text,
        "payload_version": payload_version.text,
        "payload_features": sorted(payload_features),
        "metadata": metadata.to_dict(),
        "nonce": base64.b64encode(encrypted.nonce).decode("ascii"),
        "salt": base64.b64encode(encrypted.salt).decode("ascii"),
        "ciphertext": base64.b64encode(encrypted.ciphertext).decode("ascii"),
        "tag": base64.b64encode(encrypted.tag).decode("ascii"),
        "hkdf_salt": base64.b64encode(encrypted.hkdf_salt or encrypted.salt).decode("ascii"),
        "encryption_version": encrypted.version,
        "aead": encrypted.aead,
        "kdf": encrypted.kdf,
        "kdf_parameters": encrypted.kdf_parameters,
    }
    wrapper_bytes = _canonicalise_json(wrapper_body).encode("utf-8")
    return write_frame(
        magic=WRAPPER_MAGIC,
        version=CURRENT_PACKAGE_VERSION,
        features=payload_features,
        body=wrapper_bytes,
    )


def read_package(
    data: bytes,
    passphrase: str,
    *,
    supported_versions: Iterable[str] | None = None,
    allowed_features: Iterable[str] | None = None,
) -> EncodedStream:
    if not data.startswith(WRAPPER_MAGIC):
        return _decode_legacy_package(data, passphrase, supported_versions)
    try:
        frame, remainder = read_frame(data, expected_magic=WRAPPER_MAGIC)
    except FrameFormatError as exc:
        raise ValueError("failed to parse package wrapper") from exc
    if remainder:
        raise ValueError("unexpected trailing data after wrapper frame")
    ensure_supported(frame.version)
    if frame.unknown_feature_bits:
        raise ValueError(
            f"wrapper advertises unknown feature bits: {sorted(frame.unknown_feature_bits)}"
        )
    wrapper = json.loads(frame.body.decode("utf-8"))
    wrapper_version_text = wrapper.get("version")
    if not isinstance(wrapper_version_text, str):
        raise ValueError("Unsupported package wrapper version")
    parsed_wrapper_version = parse_any_version(wrapper_version_text)
    ensure_supported(parsed_wrapper_version)
    if parsed_wrapper_version.major != frame.version.major:
        raise ValueError("wrapper version major mismatch")
    advertised_features = set(wrapper.get("payload_features", []))
    if frame.features != frozenset(advertised_features):
        raise ValueError("wrapper feature bitset mismatch")
    if allowed_features is not None:
        allowed = set(allowed_features)
        unsupported = set(frame.features) - allowed
        if unsupported:
            raise ValueError(
                f"Package requires unsupported features: {sorted(unsupported)}"
            )
    metadata_dict = wrapper.get("metadata")
    if not isinstance(metadata_dict, dict):
        raise ValueError("metadata must be an object")
    metadata = PackageMetadata.from_dict(metadata_dict)
    encrypted = EncryptionResult(
        nonce=base64.b64decode(wrapper["nonce"]),
        salt=base64.b64decode(wrapper["salt"]),
        hkdf_salt=base64.b64decode(wrapper.get("hkdf_salt", wrapper["salt"])),
        ciphertext=base64.b64decode(wrapper["ciphertext"]),
        tag=base64.b64decode(wrapper["tag"]),
        version=int(wrapper.get("encryption_version", 1)),
        aead=str(wrapper.get("aead", "chacha20poly1305")),
        kdf=str(wrapper.get("kdf", "pbkdf2")),
        kdf_parameters=_parse_kdf_parameters(wrapper),
    )
    payload_bytes = decrypt(encrypted, passphrase, metadata.to_associated_data())
    payload_frame, payload_remainder = read_frame(payload_bytes, expected_magic=PAYLOAD_MAGIC)
    if payload_remainder:
        raise ValueError("unexpected trailing data after payload frame")
    ensure_supported(payload_frame.version)
    if payload_frame.version < MINIMUM_SUPPORTED_PACKAGE_VERSION:
        raise ValueError("payload version below supported minimum")
    if payload_frame.unknown_feature_bits:
        raise ValueError(
            f"payload advertises unknown feature bits: {sorted(payload_frame.unknown_feature_bits)}"
        )
    payload_features = set(payload_frame.features)
    if payload_features != set(frame.features):
        raise ValueError("payload feature set mismatch with wrapper")
    if allowed_features is not None:
        allowed = set(allowed_features)
        unsupported = payload_features - allowed
        if unsupported:
            raise ValueError(
                f"Package requires unsupported features: {sorted(unsupported)}"
            )
    payload_version_text = wrapper.get("payload_version")
    if not isinstance(payload_version_text, str):
        raise ValueError("payload_version missing from wrapper")
    parsed_payload_version = parse_any_version(payload_version_text)
    if parsed_payload_version != payload_frame.version:
        raise ValueError("payload version mismatch between wrapper and payload")
    if supported_versions is not None:
        negotiated = {parse_any_version(value) for value in supported_versions}
        if payload_frame.version not in negotiated:
            raise ValueError(
                f"payload version {payload_frame.version.short_text} not negotiated"
            )
    return _decode_structured_payload(payload_frame.body, metadata, payload_frame.version)


def _serialise_payload(
    package: QYNPackage,
    prefer_versions: Iterable[str] | None,
    extra_features: Iterable[str] | None,
) -> Tuple[bytes, Version, Sequence[str]]:
    sections = _build_sections_from_package(package)
    body = encode_sections(sections)
    features = set(_derive_payload_features(package))
    if extra_features is not None:
        features.update(extra_features)
    payload_version = negotiate_version(prefer_versions)
    frame = write_frame(
        magic=PAYLOAD_MAGIC,
        version=payload_version,
        features=features,
        body=body,
    )
    return frame, payload_version, sorted(features)


def _derive_payload_features(package: QYNPackage) -> Iterable[str]:
    features: set[str] = set()
    if package.compression_extras is not None:
        features.add("compression:extras")
        if "optimisation" in package.compression_extras:
            features.add("compression:optimisation")
    if package.compression_backend == "fse":
        features.add("compression:fse")
    if package.source_map_bytes is not None:
        features.add("payload:source-map")
    return features


def _build_sections_from_package(package: QYNPackage) -> List[SectionRecord]:
    sections: List[SectionRecord] = []
    sections.append(_encode_stream_header_section(package))
    sections.append(_encode_compression_section(package))
    sections.append(_encode_tokens_section(package))
    sections.append(_encode_string_table_section(package))
    sections.append(_encode_payload_section(package))
    sections.extend(_encode_payload_channel_sections(package))
    if package.source_map_bytes is not None:
        sections.append(_encode_source_map_section(package))
    sections.append(_encode_metadata_section(package))
    return sections


def _encode_stream_header_section(package: QYNPackage) -> SectionRecord:
    metadata = package.metadata
    payload = bytearray()
    payload.extend(_write_utf8(package.dictionary_version))
    payload.extend(_write_utf8(package.encoder_version))
    payload.extend(_write_utf8(metadata.source_language or ""))
    payload.extend(_write_utf8(metadata.source_language_version or ""))
    payload.extend(struct.pack("<I", package.symbol_count))
    payload.append(0)  # hash type: 0 = SHA-256
    payload.extend(_decode_source_hash(metadata.source_hash))
    flags = 0
    if package.source_map_bytes is not None:
        flags |= 0x0001
    return _make_section(SECTION_STREAM_HEADER, flags, bytes(payload))


def _encode_compression_section(package: QYNPackage) -> SectionRecord:
    payload = bytearray()
    payload.extend(_write_utf8(package.compression_backend))
    payload.extend(struct.pack("<I", package.symbol_count))
    model_json = _canonicalise_json(package.compression_model).encode("utf-8")
    payload.extend(_write_u32_le(len(model_json)))
    payload.extend(model_json)
    if package.compression_extras is not None:
        extras_json = _canonicalise_json(package.compression_extras).encode("utf-8")
    else:
        extras_json = b""
    payload.extend(_write_u32_le(len(extras_json)))
    payload.extend(extras_json)
    return _make_section(SECTION_COMPRESSION, 0, bytes(payload))


# ---------------------------------------------------------------------------
# Decoding helpers


def _decode_structured_payload(
    body: bytes, wrapper_metadata: PackageMetadata, payload_version: Version
) -> EncodedStream:
    sections = _decode_section_records(body)
    return _build_stream_from_sections(sections, wrapper_metadata, payload_version)


def _encode_tokens_section(package: QYNPackage) -> SectionRecord:
    payload = bytearray()
    payload.extend(_write_u32_le(len(package.compressed_tokens)))
    payload.extend(package.compressed_tokens)
    return _make_section(SECTION_TOKENS, 0, bytes(payload))


def _encode_string_table_section(package: QYNPackage) -> SectionRecord:
    payload = bytearray()
    payload.extend(_write_u32_le(len(package.string_table_bytes)))
    payload.extend(package.string_table_bytes)
    return _make_section(SECTION_STRING_TABLE, 0, bytes(payload))


def _encode_payload_section(package: QYNPackage) -> SectionRecord:
    serializable = (
        package.payload_channels.to_serializable(
            token_keys=package.payload_channels.token_keys
        )
        if package.payload_channels is not None
        else {"entries": [], "channels": {}}
    )
    channel_map = serializable.get("channels", {}) if isinstance(serializable, dict) else {}
    channel_bits = PAYLOAD_CHANNEL_TOKEN
    channel_bits |= PAYLOAD_CHANNEL_IDENTIFIER if _channel_symbol_count(channel_map.get("I", {})) else 0
    channel_bits |= PAYLOAD_CHANNEL_STRING if _channel_symbol_count(channel_map.get("S", {})) else 0
    channel_bits |= PAYLOAD_CHANNEL_INTEGER if _channel_symbol_count(channel_map.get("N", {})) else 0
    channel_bits |= PAYLOAD_CHANNEL_COUNT if _channel_symbol_count(channel_map.get("C", {})) else 0
    channel_bits |= PAYLOAD_CHANNEL_FLAG if _channel_symbol_count(channel_map.get("F", {})) else 0
    payload_body: Dict[str, Any] = {
        "encoding_version": ENCODING_VERSION,
        "channel_bits": channel_bits,
        "entries": list(serializable.get("entries", [])),
        "structured_channel": channel_map.get("R", {}),
    }
    payload_json = _canonicalise_json(payload_body).encode("utf-8")
    payload = _write_u32_le(len(payload_json)) + payload_json
    return _make_section(SECTION_PAYLOADS, 0, payload)


def _encode_source_map_section(package: QYNPackage) -> SectionRecord:
    assert package.source_map_bytes is not None
    payload = _write_u32_le(len(package.source_map_bytes)) + package.source_map_bytes
    return _make_section(SECTION_SOURCE_MAP, 0, payload)


def _encode_metadata_section(package: QYNPackage) -> SectionRecord:
    metadata_json = _canonicalise_json(package.metadata.to_dict()).encode("utf-8")
    payload = _write_u32_le(len(metadata_json)) + metadata_json
    return _make_section(SECTION_METADATA, 0, payload)


def _encode_payload_channel_sections(package: QYNPackage) -> List[SectionRecord]:
    if package.payload_channels is None:
        return []
    serializable = package.payload_channels.to_serializable(
        token_keys=package.payload_channels.token_keys
    )
    channels = serializable.get("channels", {}) if isinstance(serializable, dict) else {}
    sections: List[SectionRecord] = []
    for channel_key, section_id in (
        ("I", SECTION_PAYLOAD_IDENTIFIERS),
        ("S", SECTION_PAYLOAD_STRINGS),
        ("N", SECTION_PAYLOAD_INTEGERS),
        ("C", SECTION_PAYLOAD_COUNTS),
        ("F", SECTION_PAYLOAD_FLAGS),
    ):
        channel_payload = channels.get(channel_key, {})
        if not _channel_symbol_count(channel_payload):
            continue
        sections.append(_encode_payload_channel_section(section_id, channel_payload))
    return sections


def _encode_payload_channel_section(section_id: int, channel_payload: Dict[str, Any]) -> SectionRecord:
    channel_json = _canonicalise_json(channel_payload).encode("utf-8")
    payload = _write_u32_le(len(channel_json)) + channel_json
    return _make_section(section_id, 0, payload)


def _channel_symbol_count(channel_payload: Dict[str, Any]) -> int:
    if not isinstance(channel_payload, dict):
        return 0
    count = channel_payload.get("symbol_count")
    return int(count) if isinstance(count, int) else 0


def _decode_section_records(payload_body: bytes) -> Dict[int, SectionRecord]:
    try:
        records = {
            section.identifier: SectionRecord(
                SectionHeader(section.identifier, section.flags, len(section.payload), 0),
                section.payload,
            )
            for section in validate_sections(decode_sections(payload_body))
        }
        return records
    except FormatError:
        return _parse_sections(payload_body)


def _build_stream_from_sections(
    sections: Dict[int, SectionRecord],
    metadata: PackageMetadata,
    payload_version: Version,
) -> EncodedStream:
    budget = ResourceBudget()
    metadata_version = parse_any_version(metadata.package_version)
    if metadata_version.major != payload_version.major:
        raise ValueError("package version mismatch between metadata and payload body")

    stream_header = _decode_stream_header_section(_require_section(sections, 0x0001))
    compression_info = _decode_compression_section(_require_section(sections, 0x0002))
    tokens_blob = _decode_tokens_section(_require_section(sections, 0x0003))
    budget.ensure_compressed(len(tokens_blob))
    string_table_bytes = _decode_string_table_section(_require_section(sections, 0x0004))
    budget.ensure_string_table(len(string_table_bytes))
    payload_section = _require_section(sections, 0x0005)
    budget.ensure_payload_bytes(len(payload_section.payload))
    payload_record = _decode_payload_section(payload_section)
    channel_bits = int(payload_record.get("channel_bits", 0))
    encoding_version = _parse_encoding_version(payload_record.get("encoding_version", "1.0"))

    source_map_bytes: Optional[bytes] = None
    if 0x0006 in sections:
        source_map_bytes = _decode_source_map_section(sections.pop(0x0006))
    if 0x0007 in sections:
        _ = _decode_metadata_section(sections.pop(0x0007))

    dictionary = load_dictionary(stream_header["dictionary_version"])
    backend_name = compression_info["backend"]
    try:
        backend = get_backend(backend_name)
    except OptionalBackendUnavailable as exc:
        raise ValueError(
            f"Compression backend '{backend_name}' is unavailable: {exc}"
        ) from exc
    model = compression_info["model"]
    budget.ensure_model(model)
    symbol_count = int(compression_info["symbol_count"])
    if stream_header["symbol_count"] != symbol_count:
        raise ValueError("symbol count mismatch between stream header and compression section")

    tokens = backend.decode(tokens_blob, model, symbol_count)
    optimisation_info = compression_info.get("optimisation")
    if isinstance(optimisation_info, dict):
        plan = TokenOptimisationPlan.from_metadata(optimisation_info)
        tokens = plan.restore(tokens)

    token_keys = [dictionary.entry_for_index(index).key for index in tokens]

    string_table = StringTable.from_bytes(string_table_bytes)
    payload_channels: PayloadChannels
    if encoding_version >= Version(1, 1, 0):
        serializable: Dict[str, Any] = {
            "entries": payload_record.get("entries", []),
            "channels": {},
        }
        channel_sections = {
            PAYLOAD_CHANNEL_IDENTIFIER: ("I", SECTION_PAYLOAD_IDENTIFIERS),
            PAYLOAD_CHANNEL_STRING: ("S", SECTION_PAYLOAD_STRINGS),
            PAYLOAD_CHANNEL_INTEGER: ("N", SECTION_PAYLOAD_INTEGERS),
            PAYLOAD_CHANNEL_COUNT: ("C", SECTION_PAYLOAD_COUNTS),
            PAYLOAD_CHANNEL_FLAG: ("F", SECTION_PAYLOAD_FLAGS),
        }
        for bit, (channel_key, section_id) in channel_sections.items():
            if not channel_bits & bit:
                continue
            section = sections.pop(section_id, None)
            if section is None:
                raise ValueError(f"payload channel section {section_id:#06x} missing")
            budget.ensure_payload_bytes(len(section.payload))
            serializable["channels"][channel_key] = _decode_payload_channel_section(section)
        structured = payload_record.get("structured_channel")
        if structured is not None:
            serializable["channels"]["R"] = structured
        payload_channels = PayloadChannels.from_serializable(
            serializable, string_table, token_keys=token_keys
        )
        payload_channels.token_keys = token_keys
        decoded_payloads = payload_channels.to_payloads(string_table)
    else:
        channels_data = payload_record.get("channels")
        if channels_data is not None:
            payload_channels = PayloadChannels.from_serializable(
                channels_data, string_table, token_keys=token_keys
            )
            payload_channels.token_keys = token_keys
            decoded_payloads = payload_channels.to_payloads(string_table)
        else:
            decoded_payloads = _materialise_payloads(payload_record, string_table)
            payload_channels = PayloadChannels.from_payloads(decoded_payloads)
    payload_channels.token_keys = token_keys

    if sections:
        sections.clear()
    source_map: Optional[SourceMap] = None
    if source_map_bytes is not None:
        try:
            source_map = SourceMap.from_bytes(source_map_bytes)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("failed to decode source map") from exc
    model_digest = _digest_model(model)
    if metadata.compression_backend != backend_name:
        raise ValueError("compression backend mismatch between wrapper and payload")
    if metadata.compression_model_digest != model_digest:
        raise ValueError("compression model digest mismatch between wrapper and payload")
    if sections:
        # Gracefully skip unknown sections.
        sections.clear()
    human_readable = dictionary.humanize(tokens)
    return EncodedStream(
        dictionary=dictionary,
        tokens=tokens,
        payloads=decoded_payloads,
        payload_channels=payload_channels,
        encoder_version=stream_header["encoder_version"],
        human_readable=human_readable,
        source_language=stream_header["source_language"],
        source_language_version=stream_header["source_language_version"],
        source_hash=stream_header["source_hash"],
        license=metadata.license,
        author=metadata.author,
        timestamp=metadata.timestamp,
        source_map=source_map,
    )


def _parse_encoding_version(value: Any) -> Version:
    if isinstance(value, str):
        digits = "".join(ch if ch.isdigit() or ch == "." else " " for ch in value)
        parts = digits.strip().split()
        if parts:
            try:
                return parse_any_version(parts[0])
            except Exception:
                pass
    return Version(1, 0, 0)


# ---------------------------------------------------------------------------
def decode_package(
    data: bytes, passphrase: str, *, budget: Optional[ResourceBudget] = None
) -> EncodedStream:
    active_budget = budget or ResourceBudget()
    if data.startswith(WRAPPER_MAGIC):
        try:
            return _decode_structured_package(data, passphrase, budget=active_budget)
        except FormatError:
            return _decode_structured_package_v1(data, passphrase, budget=active_budget)
    return _decode_legacy_package(data, passphrase, budget=active_budget)


def _decode_structured_package(
    data: bytes, passphrase: str, *, budget: ResourceBudget
) -> EncodedStream:
    wrapper_frame, remainder = decode_frame(data, expected_magic=WRAPPER_MAGIC)
    wrapper = json.loads(wrapper_frame.body.decode("utf-8"))
    wrapper_version_text = wrapper.get("version")
    if not isinstance(wrapper_version_text, str):
        raise ValueError("Unsupported package wrapper version")
    parsed_wrapper_version = parse_any_version(wrapper_version_text)
    ensure_supported(parsed_wrapper_version)
    if wrapper_frame.version.major != parsed_wrapper_version.major:
        raise ValueError("wrapper version major mismatch")
    metadata_dict = wrapper.get("metadata")
    if not isinstance(metadata_dict, dict):
        raise ValueError("metadata must be an object")
    metadata = PackageMetadata.from_dict(metadata_dict)
    associated_data = metadata.to_associated_data()
    encrypted = EncryptionResult(
        nonce=base64.b64decode(wrapper["nonce"]),
        salt=base64.b64decode(wrapper["salt"]),
        hkdf_salt=base64.b64decode(wrapper.get("hkdf_salt", wrapper["salt"])),
        ciphertext=base64.b64decode(wrapper["ciphertext"]),
        tag=base64.b64decode(wrapper["tag"]),
        version=int(wrapper.get("encryption_version", 1)),
        aead=str(wrapper.get("aead", "chacha20poly1305")),
        kdf=str(wrapper.get("kdf", "pbkdf2")),
        kdf_parameters=_parse_kdf_parameters(wrapper),
    )
    payload_envelope = decrypt(encrypted, passphrase, associated_data)
    budget.ensure_payload_bytes(len(payload_envelope))
    payload_header, payload_remainder = decode_frame(
        payload_envelope, expected_magic=PAYLOAD_MAGIC
    )
    payload_body = payload_header.body
    ensure_supported(payload_header.version)
    payload_version_text = wrapper.get("payload_version")
    if isinstance(payload_version_text, str):
        declared_payload_version = parse_any_version(payload_version_text)
        if declared_payload_version.major != payload_header.version.major:
            raise ValueError("payload version mismatch between wrapper and payload")
    sections = _decode_section_records(payload_body)
    return _build_stream_from_sections(sections, metadata, payload_header.version)


def _decode_structured_package_v1(
    data: bytes, passphrase: str, *, budget: ResourceBudget
) -> EncodedStream:
    header_version, wrapper_bytes, remainder = _split_wrapper(data)
    if remainder:
        raise ValueError("unexpected trailing data after wrapper envelope")
    wrapper = json.loads(wrapper_bytes.decode("utf-8"))
    wrapper_version_text = wrapper.get("version")
    if not isinstance(wrapper_version_text, str):
        raise ValueError("Unsupported package wrapper version")
    parsed_wrapper_version = parse_any_version(wrapper_version_text)
    ensure_supported(parsed_wrapper_version)
    if header_version.major != parsed_wrapper_version.major:
        raise ValueError("wrapper version major mismatch")
    metadata_dict = wrapper.get("metadata")
    if not isinstance(metadata_dict, dict):
        raise ValueError("metadata must be an object")
    metadata = PackageMetadata.from_dict(metadata_dict)
    associated_data = metadata.to_associated_data()
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
            key: int(value)
            for key, value in dict(wrapper.get("kdf_parameters", {})).items()
        },
    )
    payload_envelope = decrypt(encrypted, passphrase, associated_data)
    budget.ensure_payload_bytes(len(payload_envelope))
    payload_version, payload_body = _split_payload(payload_envelope)
    ensure_supported(payload_version)
    payload_version_text = wrapper.get("payload_version")
    if isinstance(payload_version_text, str):
        declared_payload_version = parse_any_version(payload_version_text)
        if declared_payload_version.major != payload_version.major:
            raise ValueError("payload version mismatch between wrapper and payload")
    sections = _decode_section_records(payload_body)
    return _build_stream_from_sections(sections, metadata, payload_version)


def _decode_legacy_package(
    data: bytes,
    passphrase: str,
    supported_versions: Iterable[str] | None = None,
    *,
    budget: Optional[ResourceBudget] = None,
) -> EncodedStream:
    active_budget = budget or ResourceBudget()
    wrapper = json.loads(data.decode("utf-8"))
    wrapper_version = wrapper.get("version")
    if not isinstance(wrapper_version, str):
        raise ValueError("Unsupported package wrapper version")
    parsed_wrapper_version = parse_any_version(wrapper_version)
    ensure_supported(parsed_wrapper_version)
    metadata_dict = wrapper.get("metadata")
    metadata: Optional[PackageMetadata]
    if metadata_dict is None:
        associated_data = LEGACY_ASSOCIATED_DATA
        metadata = None
    else:
        if not isinstance(metadata_dict, dict):
            raise ValueError("metadata must be an object")
        metadata = PackageMetadata.from_dict(metadata_dict)
        associated_data = metadata.to_associated_data()
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
            key: int(value)
            for key, value in dict(wrapper.get("kdf_parameters", {})).items()
        },
    )
    plaintext = decrypt(encrypted, passphrase, associated_data)
    active_budget.ensure_payload_bytes(len(plaintext))
    payload = json.loads(plaintext.decode("utf-8"))
    payload_version = payload.get("version")
    if not isinstance(payload_version, str):
        raise ValueError("Unsupported payload version")
    parsed_payload_version = parse_any_version(payload_version)
    ensure_supported(parsed_payload_version)
    if supported_versions is not None:
        negotiated = {parse_any_version(value) for value in supported_versions}
        if parsed_payload_version not in negotiated:
            raise ValueError(
                f"payload version {parsed_payload_version.short_text} not negotiated"
            )
    dictionary_version = payload.get("dictionary_version")
    if not isinstance(dictionary_version, str):
        raise ValueError("dictionary_version missing from payload")
    dictionary = load_dictionary(dictionary_version)
    source_map: Optional[SourceMap] = None
    if parsed_payload_version.short_text == "1.0":
        table_info = payload["table"]
        table = RANSTable(
            precision_bits=table_info["precision_bits"],
            frequencies=table_info["frequencies"],
            cumulative=_build_cumulative(table_info["frequencies"]),
            lookup=_build_lookup(table_info["frequencies"], table_info["precision_bits"]),
        )
        compressed = base64.b64decode(payload["compressed_tokens"])
        active_budget.ensure_compressed(len(compressed))
        codec = RANSCodec(table.precision_bits)
        symbol_count = payload.get("symbol_count")
        if not isinstance(symbol_count, int):
            raise ValueError("symbol_count missing from payload")
        active_budget.ensure_symbols(symbol_count)
        active_budget.ensure_model(
            {
                "precision_bits": table.precision_bits,
                "frequencies": table_info["frequencies"],
            }
        )
        tokens = codec.decode(compressed, table, symbol_count)
        decoded_payloads = [Payload(**item) for item in payload.get("payloads", [])]
        decoded_payloads = _normalise_payloads(decoded_payloads)
        compression_backend = "rans"
        model_digest = _digest_model(
            {
                "precision_bits": table.precision_bits,
                "frequencies": table_info["frequencies"],
            }
        )
    else:
        compression = payload.get("compression", {})
        backend_name = compression.get("backend", "rans")
        try:
            backend = get_backend(backend_name)
        except OptionalBackendUnavailable as exc:
            raise ValueError(
                f"Compression backend '{backend_name}' is unavailable: {exc}"
            ) from exc
        model = compression.get("model")
        if not isinstance(model, dict):
            raise ValueError("compression model missing from payload")
        active_budget.ensure_model(model)
        compressed = base64.b64decode(payload["compressed_tokens"])
        active_budget.ensure_compressed(len(compressed))
        symbol_count = compression.get("symbol_count")
        if not isinstance(symbol_count, int):
            raise ValueError("symbol_count missing from payload")
        active_budget.ensure_symbols(symbol_count)
        optimisation_info = compression.get("optimisation")
        optimisation_plan: Optional[TokenOptimisationPlan] = None
        if isinstance(optimisation_info, dict):
            optimisation_plan = TokenOptimisationPlan.from_metadata(optimisation_info)
        tokens = decompress_internal(
            backend,
            compressed,
            model,
            symbol_count,
            budget=active_budget,
        )
        if optimisation_plan is not None:
            tokens = optimisation_plan.restore(tokens)
        table_bytes = base64.b64decode(payload["string_table"])
        active_budget.ensure_string_table(len(table_bytes))
        string_table = StringTable.from_bytes(table_bytes)
        payloads_data = payload.get("payloads", [])
        decoded_payloads = []
        for entry in payloads_data:
            decoded = string_table.decode_payload(entry)
            decoded_payloads.append(Payload(decoded["type"], decoded["value"]))
        decoded_payloads = _normalise_payloads(decoded_payloads)
        compression_backend = backend.name
        model_digest = _digest_model(model)
    source_map_blob = payload.get("source_map")
    if isinstance(source_map_blob, str):
        try:
            source_map = SourceMap.from_bytes(base64.b64decode(source_map_blob))
        except Exception as exc:
            raise ValueError("failed to decode source map") from exc
    inner_metadata = payload.get("metadata")
    if isinstance(inner_metadata, dict):
        payload_metadata = PackageMetadata.from_dict(inner_metadata)
        if metadata is None:
            metadata = payload_metadata
        elif payload_metadata.to_dict() != metadata.to_dict():
            raise ValueError("metadata mismatch between wrapper and payload")
    human_readable = dictionary.humanize(tokens)
    payload_channels = PayloadChannels.from_payloads(decoded_payloads)
    if metadata is None:
        metadata = PackageMetadata(
            package_version=parsed_payload_version.text,
            dictionary_version=dictionary_version,
            encoder_version=payload.get("encoder_version", "unknown"),
            source_language=str(payload.get("source_language", "unknown")),
            source_language_version=str(payload.get("source_language_version", "unknown")),
            source_hash=str(payload.get("source_hash", "")),
            compression_backend=compression_backend,
            compression_model_digest=model_digest,
            symbol_count=len(tokens),
        )
        return EncodedStream(
            dictionary=dictionary,
            tokens=tokens,
            payloads=decoded_payloads,
            payload_channels=payload_channels,
            encoder_version=payload.get("encoder_version", "unknown"),
            human_readable=human,
            source_language=metadata.source_language,
            source_language_version=metadata.source_language_version,
            source_hash=metadata.source_hash,
            license=metadata.license,
            author=metadata.author,
            timestamp=metadata.timestamp,
            source_map=source_map,
        )
    return EncodedStream(
        dictionary=dictionary,
        tokens=tokens,
        payloads=decoded_payloads,
        payload_channels=payload_channels,
        encoder_version=payload.get("encoder_version", "unknown"),
        human_readable=human_readable,
        source_language=str(payload.get("source_language", "unknown")),
        source_language_version=str(payload.get("source_language_version", "unknown")),
        source_hash=str(payload.get("source_hash", "")),
        license=metadata.license,
        author=metadata.author,
        timestamp=metadata.timestamp,
        source_map=source_map,
    )


# ---------------------------------------------------------------------------
# Backward compatibility helpers
def _split_wrapper(data: bytes) -> Tuple[Version, bytes, bytes]:
    header, remainder = WrapperHeader.parse(data)
    body, trailing = header.split_body(remainder)
    return header.version, body, trailing


def _split_payload(data: bytes) -> Tuple[Version, bytes]:
    header, remainder = PayloadHeader.parse(data)
    body, trailing = header.split_body(remainder)
    if trailing:
        raise HeaderFormatError("unexpected trailing data after payload envelope")
    return header.version, body


def _parse_sections(buffer: bytes) -> Dict[int, SectionRecord]:
    sections: Dict[int, SectionRecord] = {}
    for section in validate_sections(decode_sections(buffer)):
        header = SectionHeader(section.identifier, section.flags, len(section.payload), 0)
        sections[section.identifier] = SectionRecord(header, section.payload)
    return sections


def _require_section(sections: Dict[int, SectionRecord], sid: int) -> SectionRecord:
    try:
        return sections.pop(sid)
    except KeyError as exc:
        raise ValueError(f"required section 0x{sid:04x} missing") from exc


def _decode_stream_header_section(section: SectionRecord) -> Dict[str, Any]:
    flags = section.header.flags
    payload = section.payload
    offset = 0
    dictionary_version, offset = _read_utf8(payload, offset)
    encoder_version, offset = _read_utf8(payload, offset)
    source_language, offset = _read_utf8(payload, offset)
    source_language_version, offset = _read_utf8(payload, offset)
    if offset + 4 > len(payload):
        raise ValueError("stream header truncated before symbol count")
    (symbol_count,) = struct.unpack_from("<I", payload, offset)
    offset += 4
    if offset >= len(payload):
        raise ValueError("stream header truncated before hash type")
    hash_type = payload[offset]
    offset += 1
    if hash_type != 0:
        raise ValueError("unsupported source hash type")
    if offset + 32 > len(payload):
        raise ValueError("stream header truncated before hash payload")
    source_hash_bytes = payload[offset : offset + 32]
    offset += 32
    if offset != len(payload):
        raise ValueError("unexpected data in stream header section")
    if source_hash_bytes == b"\x00" * 32:
        source_hash = ""
    else:
        source_hash = source_hash_bytes.hex()
    return {
        "dictionary_version": dictionary_version,
        "encoder_version": encoder_version,
        "source_language": source_language,
        "source_language_version": source_language_version,
        "symbol_count": symbol_count,
        "source_hash": source_hash,
        "flags": flags,
    }


def _decode_compression_section(section: SectionRecord) -> Dict[str, Any]:
    payload = section.payload
    offset = 0
    backend, offset = _read_utf8(payload, offset)
    if offset + 4 > len(payload):
        raise ValueError("compression section truncated before symbol count")
    (symbol_count,) = struct.unpack_from("<I", payload, offset)
    offset += 4
    model_length, offset = _read_u32_from(payload, offset)
    end = offset + model_length
    if end > len(payload):
        raise ValueError("compression model payload truncated")
    model = json.loads(payload[offset:end].decode("utf-8")) if model_length else {}
    offset = end
    extras_length, offset = _read_u32_from(payload, offset)
    extras_dict: Optional[Dict[str, Any]] = None
    if extras_length:
        end = offset + extras_length
        if end > len(payload):
            raise ValueError("compression extras truncated")
        extras_dict = json.loads(payload[offset:end].decode("utf-8"))
        offset = end
    if offset != len(payload):
        raise ValueError("unexpected data in compression section")
    result: Dict[str, Any] = {
        "backend": backend,
        "symbol_count": symbol_count,
        "model": model,
    }
    if extras_dict is not None:
        result["extras"] = extras_dict
        optimisation = extras_dict.get("optimisation")
        if isinstance(optimisation, dict):
            result["optimisation"] = optimisation
    return result


def _decode_tokens_section(section: SectionRecord) -> bytes:
    payload = section.payload
    if len(payload) < 4:
        raise ValueError("compressed token section too small")
    (length,) = struct.unpack_from("<I", payload, 0)
    data = payload[4 : 4 + length]
    if len(data) != length:
        raise ValueError("compressed token payload truncated")
    if len(payload) != 4 + length:
        raise ValueError("unexpected data in compressed token section")
    return data


def _decode_string_table_section(section: SectionRecord) -> bytes:
    return _decode_length_prefixed_bytes(section.payload)


def _decode_payload_section(section: SectionRecord) -> Dict[str, Any]:
    return _decode_length_prefixed_json(section.payload)


def _decode_payload_channel_section(section: SectionRecord) -> Dict[str, Any]:
    return _decode_length_prefixed_json(section.payload)


def _decode_source_map_section(section: SectionRecord) -> bytes:
    return _decode_length_prefixed_bytes(section.payload)


def _decode_metadata_section(section: SectionRecord) -> Dict[str, Any]:
    return _decode_length_prefixed_json(section.payload)


@dataclass
class PackageEnvelope:
    """Container exposing metadata and decrypted payload for inspection."""

    metadata: PackageMetadata
    payload: bytes
    wrapper_version: Version
    structured: bool
    dictionary_version: str
    encoder_version: str


def read_package(data: bytes, passphrase: str) -> PackageEnvelope:
    """Decrypt *data* and return metadata alongside the raw payload."""

    structured, wrapper_version, wrapper, remainder = _extract_wrapper_components(data)
    if remainder:
        raise ValueError("unexpected trailing data after wrapper envelope")
    metadata_dict = wrapper.get("metadata")
    metadata: Optional[PackageMetadata]
    if metadata_dict is None:
        associated_data = LEGACY_ASSOCIATED_DATA
        metadata = None
    else:
        if not isinstance(metadata_dict, dict):
            raise ValueError("metadata must be an object")
        metadata = PackageMetadata.from_dict(metadata_dict)
        associated_data = metadata.to_associated_data()
    encrypted = EncryptionResult(
        nonce=base64.b64decode(wrapper["nonce"]),
        salt=base64.b64decode(wrapper["salt"]),
        hkdf_salt=base64.b64decode(wrapper.get("hkdf_salt", wrapper["salt"])),
        ciphertext=base64.b64decode(wrapper["ciphertext"]),
        tag=base64.b64decode(wrapper["tag"]),
        version=int(wrapper.get("encryption_version", 1)),
        aead=str(wrapper.get("aead", "chacha20poly1305")),
        kdf=str(wrapper.get("kdf", "pbkdf2")),
        kdf_parameters=_parse_kdf_parameters(wrapper),
    )
    payload = decrypt(encrypted, passphrase, associated_data)
    if not structured:
        payload_dict = json.loads(payload.decode("utf-8"))
        if metadata is None:
            compression_section = payload_dict.get("compression", {})
            if not isinstance(compression_section, dict):
                compression_section = {}
            model_dict = compression_section.get("model", {})
            if not isinstance(model_dict, dict):
                model_dict = {}
            metadata = PackageMetadata(
                package_version=str(payload_dict.get("version", "1.0")),
                dictionary_version=str(payload_dict.get("dictionary_version", "1.0")),
                encoder_version=str(payload_dict.get("encoder_version", "unknown")),
                source_language=str(payload_dict.get("source_language", "unknown")),
                source_language_version=str(
                    payload_dict.get("source_language_version", "unknown")
                ),
                source_hash=str(payload_dict.get("source_hash", "")),
                compression_backend=str(
                    compression_section.get("backend", "rans")
                ),
                compression_model_digest=_digest_model(model_dict),
                symbol_count=int(compression_section.get("symbol_count", 0)),
            )
    assert metadata is not None
    return PackageEnvelope(
        metadata=metadata,
        payload=payload,
        wrapper_version=wrapper_version,
        structured=structured,
        dictionary_version=metadata.dictionary_version,
        encoder_version=metadata.encoder_version,
    )


def decode_stream(payload: bytes) -> Dict[str, Any]:
    """Decode a structured payload into its component sections."""

    payload_version, body = _split_payload(payload)
    ensure_supported(payload_version)
    sections = _parse_sections(body)
    stream_header = _decode_stream_header_section(_require_section(sections, 0x0001))
    compression_info = _decode_compression_section(_require_section(sections, 0x0002))
    tokens_blob = _decode_tokens_section(_require_section(sections, 0x0003))
    string_table = _decode_string_table_section(_require_section(sections, 0x0004))
    payload_records = _decode_payload_section(_require_section(sections, 0x0005))
    result: Dict[str, Any] = {
        "payload_version": payload_version.text,
        "stream": stream_header,
        "compression": {
            "backend": compression_info["backend"],
            "symbol_count": compression_info["symbol_count"],
            "model": compression_info["model"],
            "payload": tokens_blob,
        },
        "string_table": string_table,
        "payloads": payload_records,
    }
    optimisation = compression_info.get("optimisation")
    if optimisation is not None:
        result["compression"]["optimisation"] = optimisation
    if 0x0006 in sections:
        result["source_map"] = _decode_source_map_section(sections.pop(0x0006))
    if 0x0007 in sections:
        result["metadata"] = _decode_metadata_section(sections.pop(0x0007))
    return result


def _extract_wrapper_components(data: bytes) -> Tuple[bool, Version, Dict[str, Any], bytes]:
    if data.startswith(WRAPPER_MAGIC):
        try:
            header, remainder = decode_frame(data, expected_magic=WRAPPER_MAGIC)
            wrapper_bytes = header.body
        except FormatError:
            version, wrapper_bytes, remainder = _split_wrapper(data)
            wrapper = json.loads(wrapper_bytes.decode("utf-8"))
            return True, version, wrapper, remainder
        wrapper = json.loads(wrapper_bytes.decode("utf-8"))
        return True, header.version, wrapper, remainder
    wrapper = json.loads(data.decode("utf-8"))
    version_value = wrapper.get("version", "1.0")
    version = parse_any_version(str(version_value))
    return False, version, wrapper, b""


def _assemble_wrapper_components(
    structured: bool, version: Version, wrapper: Dict[str, Any], remainder: bytes = b""
) -> bytes:
    if structured:
        wrapper_json = _canonicalise_json(wrapper).encode("utf-8")
        frame = encode_frame(
            magic=WRAPPER_MAGIC,
            version=version,
            features=wrapper.get("payload_features", ()),
            body=wrapper_json,
        )
        return frame + remainder
    return json.dumps(wrapper).encode("utf-8")


# Backward compatibility helpers ------------------------------------------------


def _build_cumulative(freqs: List[int]) -> List[int]:
    cumulative = []
    total = 0
    for freq in freqs:
        cumulative.append(total)
        total += freq
    return cumulative


def _build_lookup(freqs: List[int], precision_bits: int) -> List[int]:
    lookup = [0] * (1 << precision_bits)
    total = 0
    for index, freq in enumerate(freqs):
        for offset in range(freq):
            lookup[total + offset] = index
        total += freq
    return lookup


def _normalise_payloads(payloads: List[Payload]) -> List[Payload]:
    return [_normalise_payload(payload) for payload in payloads]


def _normalise_payload(payload: Payload) -> Payload:
    return Payload(payload.type, _normalise_value(payload.value))


def _normalise_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalise_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_normalise_value(item) for item in value]
    if isinstance(value, list):
        return [_normalise_value(item) for item in value]
    return value


__all__ = [
    "QYNPackage",
    "PackageMetadata",
    "encode_package",
    "write_package",
    "read_package",
    "decode_package",
]
