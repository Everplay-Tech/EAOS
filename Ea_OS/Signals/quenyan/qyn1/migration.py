"""Utilities for migrating MCS packages across dictionary revisions."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Sequence, Tuple

from .dictionary import (
    MorphemeDictionary,
    UnknownMorphemeError,
    ensure_dictionary_supported,
    load_dictionary,
)
from .encoder import EncodedStream
from .package import decode_package, encode_package
from .versioning import CURRENT_PACKAGE_VERSION, Version, ensure_supported, parse_any_version
from .crypto import encrypt


@dataclass
class MigrationReport:
    """Summary of a migration operation."""

    tokens_migrated: int
    missing_keys: List[str]
    dictionary_version: str
    package_version: str


def _build_token_map(
    source: MorphemeDictionary,
    target: MorphemeDictionary,
    *,
    strict: bool = False,
) -> Tuple[List[int], List[str]]:
    missing: List[str] = []
    mapping: List[int] = []
    fallback = target.index_for_key("meta:unknown")
    for index in range(len(source)):
        key = source.key_for_index(index)
        entry = target.entry_for_key(key)
        if entry is None:
            if strict:
                raise UnknownMorphemeError(
                    f"Target dictionary {target.version} missing morpheme key {key!r}"
                )
            missing.append(key)
            mapping.append(fallback)
        else:
            mapping.append(target.index_for_key(key))
    return mapping, missing


def _remap_tokens(tokens: Sequence[int], mapping: Sequence[int]) -> List[int]:
    return [mapping[token] for token in tokens]


def migrate_stream(
    stream: EncodedStream,
    *,
    target_dictionary: str | None = None,
    target_package_version: Version | None = None,
    strict_morpheme_errors: bool = False,
) -> Tuple[EncodedStream, MigrationReport]:
    dictionary_version = target_dictionary or stream.dictionary.version
    package_version = target_package_version or CURRENT_PACKAGE_VERSION
    try:
        ensure_dictionary_supported(dictionary_version, package_version=package_version)
    except ValueError as exc:
        raise ValueError(
            f"Dictionary version {dictionary_version} incompatible with target package "
            f"{package_version.text}: {exc}"
        ) from exc
    target_dictionary_obj = load_dictionary(
        dictionary_version, strict_morpheme_errors=strict_morpheme_errors
    )
    mapping, missing = _build_token_map(
        stream.dictionary, target_dictionary_obj, strict=strict_morpheme_errors
    )
    migrated_tokens = _remap_tokens(stream.tokens, mapping)
    migrated_stream = EncodedStream(
        dictionary=target_dictionary_obj,
        tokens=migrated_tokens,
        payloads=list(stream.payloads),
        payload_channels=stream.payload_channels,
        encoder_version=stream.encoder_version,
        human_readable=target_dictionary_obj.humanize(migrated_tokens),
        source_language=stream.source_language,
        source_language_version=stream.source_language_version,
        source_hash=stream.source_hash,
        license=stream.license,
        author=stream.author,
        timestamp=stream.timestamp,
        source_map=stream.source_map,
    )
    report = MigrationReport(
        tokens_migrated=len(migrated_tokens),
        missing_keys=sorted(set(missing)),
        dictionary_version=target_dictionary_obj.version,
        package_version=package_version.text,
    )
    return migrated_stream, report


def _serialise_for_version(package, passphrase: str, target_version: str) -> bytes:
    version = parse_any_version(target_version)
    ensure_supported(version)
    if version == CURRENT_PACKAGE_VERSION:
        return package.to_bytes(passphrase)
    if version.short_text == "1.0":
        raise ValueError("Downgrading to 1.0 format is not supported")
    metadata = replace(package.metadata, package_version=version.text)
    payload = package.to_json()
    payload["version"] = version.text
    payload["metadata"] = metadata.to_dict()
    plaintext = json.dumps(payload).encode("utf-8")
    associated = metadata.to_associated_data()
    encrypted = encrypt(plaintext, passphrase, associated)
    wrapper = {
        "version": version.text,
        "metadata": metadata.to_dict(),
        "nonce": base64.b64encode(encrypted.nonce).decode("ascii"),
        "salt": base64.b64encode(encrypted.salt).decode("ascii"),
        "ciphertext": base64.b64encode(encrypted.ciphertext).decode("ascii"),
        "tag": base64.b64encode(encrypted.tag).decode("ascii"),
    }
    return json.dumps(wrapper).encode("utf-8")


def migrate_bytes(
    data: bytes,
    passphrase: str,
    *,
    target_dictionary: str | None = None,
    target_package_version: str | None = None,
    strict_morpheme_errors: bool = False,
) -> Tuple[bytes, MigrationReport]:
    stream = decode_package(data, passphrase)
    package_version_text = target_package_version or CURRENT_PACKAGE_VERSION.text
    package_version = parse_any_version(package_version_text)
    migrated_stream, report = migrate_stream(
        stream,
        target_dictionary=target_dictionary,
        target_package_version=package_version,
        strict_morpheme_errors=strict_morpheme_errors,
    )
    package = encode_package(migrated_stream)
    migrated_bytes = _serialise_for_version(package, passphrase, package_version_text)
    report.package_version = package_version.text
    report.dictionary_version = migrated_stream.dictionary.version
    return migrated_bytes, report


def migrate_file(
    input_path: Path,
    output_path: Path,
    passphrase: str,
    *,
    target_dictionary: str | None = None,
    target_package_version: str | None = None,
    strict_morpheme_errors: bool = False,
) -> MigrationReport:
    data = input_path.read_bytes()
    migrated, report = migrate_bytes(
        data,
        passphrase,
        target_dictionary=target_dictionary,
        target_package_version=target_package_version,
        strict_morpheme_errors=strict_morpheme_errors,
    )
    output_path.write_bytes(migrated)
    return report
