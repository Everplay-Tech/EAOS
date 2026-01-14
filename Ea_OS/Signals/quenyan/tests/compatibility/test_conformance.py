import base64
import json
from pathlib import Path

import pytest

from qyn1.crypto import EncryptionResult, decrypt
from qyn1.encoder import QYNEncoder
from qyn1.format import (
    PAYLOAD_FLAG_CANONICAL_SECTIONS,
    PAYLOAD_MAGIC,
    WRAPPER_FLAG_ENCRYPTED,
    WRAPPER_FLAG_METADATA_AUTHENTICATED,
    WRAPPER_MAGIC,
    decode_frame,
    decode_sections,
)
from qyn1.package import decode_package, encode_package

SAMPLE_SOURCE = """
from math import factorial


def demo(value: int) -> int:
    return factorial(value)
""".strip()

ARCHIVE_ROOT = Path(__file__).resolve().parents[1] / "data" / "compatibility"


def _decrypt_ciphertext(wrapper: dict, passphrase: str) -> bytes:
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
    aad = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    associated = f"QYN1-METADATA-v1:{aad}".encode("utf-8")
    return decrypt(encrypted, passphrase, associated)


def test_new_framing_round_trip() -> None:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    package = encode_package(stream)
    blob = package.to_bytes("compatibility")

    wrapper_header, wrapper_payload, wrapper_remainder = decode_frame(
        blob, expected_magic=WRAPPER_MAGIC
    )
    assert wrapper_remainder == b""
    assert wrapper_header.flags & WRAPPER_FLAG_ENCRYPTED
    assert wrapper_header.flags & WRAPPER_FLAG_METADATA_AUTHENTICATED

    wrapper = json.loads(wrapper_payload.decode("utf-8"))
    payload_envelope = _decrypt_ciphertext(wrapper, "compatibility")
    payload_header, payload_body, payload_remainder = decode_frame(
        payload_envelope, expected_magic=PAYLOAD_MAGIC
    )
    assert payload_remainder == b""
    assert payload_header.flags & PAYLOAD_FLAG_CANONICAL_SECTIONS

    sections = decode_sections(payload_body)
    assert {0x0001, 0x0002, 0x0003, 0x0004, 0x0005}.issubset(set(sections.keys()))

    decoded = decode_package(blob, "compatibility")
    assert decoded.dictionary_version == stream.dictionary_version
    assert decoded.tokens == stream.tokens


@pytest.mark.parametrize("path", sorted(ARCHIVE_ROOT.rglob("*.mcs")))
def test_legacy_archives_decode(path: Path) -> None:
    payload = path.read_bytes()
    stream = decode_package(payload, "compatibility")
    assert stream.tokens
    assert stream.dictionary_version
