"""Generate archived MCS files for cross-version compatibility tests."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from qyn1.compression import RANSCodec
from qyn1.crypto import encrypt
from qyn1.encoder import QYNEncoder
from qyn1.package import LEGACY_ASSOCIATED_DATA, PackageMetadata, encode_package
from qyn1.versioning import CURRENT_PACKAGE_VERSION


PASSPHRASE = "compatibility"
OUTPUT_ROOT = Path("tests/data/compatibility")


SOURCES: Sequence[str] = (
    """\
def add(a, b):
    return a + b
""",
    """\
class Greeter:
    def __init__(self, name: str):
        self._name = name

    def greet(self) -> str:
        return f"Hello, {self._name}!"
""",
    """\
async def fetch(session, url):
    async with session.get(url) as response:
        return await response.text()
""",
    """\
def factorial(n: int) -> int:
    if n < 2:
        return 1
    return n * factorial(n - 1)
""",
    """\
def accumulate(values):
    total = 0
    for value in values:
        if value % 2 == 0:
            total += value
    return total
""",
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    path.write_text(text)


def _serialise_current(
    stream,
    *,
    version: str,
    include_source_map: bool,
    include_payload_metadata: bool,
    include_compression_meta: bool,
    ordinal: int,
    directory: Path,
) -> None:
    package = encode_package(stream)
    metadata = replace(package.metadata, package_version=version)
    payload_dict = package.to_json()
    payload_dict["version"] = version
    associated = metadata.to_associated_data()
    wrapper_metadata = metadata.to_dict()
    if include_payload_metadata:
        payload_dict.setdefault("metadata", wrapper_metadata)
        payload_dict["metadata"]["package_version"] = version
    else:
        payload_dict.pop("metadata", None)
        wrapper_metadata = None
        associated = LEGACY_ASSOCIATED_DATA
    if not include_source_map:
        payload_dict.pop("source_map", None)
    if not include_compression_meta:
        compression = payload_dict.get("compression", {})
        compression.pop("optimisation", None)
        compression.pop("mode", None)
    plaintext = json.dumps(payload_dict).encode("utf-8")
    encrypted = encrypt(plaintext, PASSPHRASE, associated)
    wrapper = {
        "version": version,
        "nonce": base64.b64encode(encrypted.nonce).decode("ascii"),
        "salt": base64.b64encode(encrypted.salt).decode("ascii"),
        "ciphertext": base64.b64encode(encrypted.ciphertext).decode("ascii"),
        "tag": base64.b64encode(encrypted.tag).decode("ascii"),
    }
    if wrapper_metadata is not None:
        wrapper["metadata"] = wrapper_metadata
    path = directory / f"sample_{ordinal:03d}.mcs"
    _write_json(path, wrapper)


def _serialise_legacy(stream, *, include_metadata: bool, include_source_map: bool, ordinal: int, directory: Path) -> None:
    codec = RANSCodec()
    table = codec.build_table(stream.tokens, len(stream.dictionary))
    compressed = codec.encode(list(stream.tokens), table)
    payloads = [payload.__dict__ for payload in stream.payloads]
    payload_dict = {
        "version": "1.0",
        "dictionary_version": stream.dictionary_version,
        "encoder_version": stream.encoder_version,
        "source_language": stream.source_language,
        "source_language_version": stream.source_language_version,
        "source_hash": stream.source_hash,
        "table": {
            "precision_bits": table.precision_bits,
            "frequencies": table.frequencies,
        },
        "compressed_tokens": base64.b64encode(compressed).decode("ascii"),
        "symbol_count": len(stream.tokens),
        "payloads": payloads,
    }
    if include_source_map and stream.source_map is not None:
        payload_dict["source_map"] = base64.b64encode(stream.source_map.to_bytes()).decode("ascii")
    metadata = None
    if include_metadata:
        metadata = PackageMetadata(
            package_version="1.0",
            dictionary_version=stream.dictionary_version,
            encoder_version=stream.encoder_version,
            source_language=stream.source_language,
            source_language_version=stream.source_language_version,
            source_hash=stream.source_hash,
            compression_backend="rans",
            compression_model_digest="legacy",
            symbol_count=len(stream.tokens),
        )
        payload_dict["metadata"] = metadata.to_dict()
    plaintext = json.dumps(payload_dict).encode("utf-8")
    associated = (
        metadata.to_associated_data() if metadata is not None else LEGACY_ASSOCIATED_DATA
    )
    encrypted = encrypt(plaintext, PASSPHRASE, associated)
    wrapper = {
        "version": "1.0",
        "nonce": base64.b64encode(encrypted.nonce).decode("ascii"),
        "salt": base64.b64encode(encrypted.salt).decode("ascii"),
        "ciphertext": base64.b64encode(encrypted.ciphertext).decode("ascii"),
        "tag": base64.b64encode(encrypted.tag).decode("ascii"),
    }
    if metadata is not None:
        wrapper["metadata"] = metadata.to_dict()
    path = directory / f"legacy_{ordinal:03d}.mcs"
    _write_json(path, wrapper)


def build_archive() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    encoder = QYNEncoder()
    legacy_dir = OUTPUT_ROOT / "1.0"
    modern_v1_dir = OUTPUT_ROOT / "1.1.0"
    modern_v2_dir = OUTPUT_ROOT / CURRENT_PACKAGE_VERSION.text
    for target in (legacy_dir, modern_v1_dir, modern_v2_dir):
        target.mkdir(parents=True, exist_ok=True)
        for file in target.glob("*.mcs"):
            file.unlink()
    legacy_counter = 0
    v1_counter = 0
    current_counter = 0
    for source in SOURCES:
        stream = encoder.encode(source)
        for include_metadata in (False, True):
            for include_source_map in (False, True):
                legacy_counter += 1
                _serialise_legacy(
                    stream,
                    include_metadata=include_metadata,
                    include_source_map=include_source_map,
                    ordinal=legacy_counter,
                    directory=legacy_dir,
                )
        for include_source_map in (False, True):
            for include_payload_metadata in (False, True):
                for include_compression_meta in (False, True):
                    v1_counter += 1
                    _serialise_current(
                        stream,
                        version="1.1.0",
                        include_source_map=include_source_map,
                        include_payload_metadata=include_payload_metadata,
                        include_compression_meta=include_compression_meta,
                        ordinal=v1_counter,
                        directory=modern_v1_dir,
                    )
                    current_counter += 1
                    _serialise_current(
                        stream,
                        version=CURRENT_PACKAGE_VERSION.text,
                        include_source_map=include_source_map,
                        include_payload_metadata=include_payload_metadata,
                        include_compression_meta=include_compression_meta,
                        ordinal=current_counter,
                        directory=modern_v2_dir,
                    )


if __name__ == "__main__":
    build_archive()

