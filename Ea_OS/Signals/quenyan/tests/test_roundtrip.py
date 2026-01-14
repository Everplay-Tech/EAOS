import ast
import hashlib
import json

import ast
import hashlib
import json

import pytest

import qyn1.package as package_module
from qyn1 import (
    QYNDecoder,
    QYNEncoder,
    available_backends,
    decode_package,
    encode_package,
)
from qyn1.package import _assemble_wrapper_components, _extract_wrapper_components
from qyn1.format import read_frame, write_frame
from qyn1.compression_config import get_compression_config
from qyn1.dictionary import load_dictionary
from qyn1.token_optimisation import build_frequency_plan
from qyn1.string_table import StringTable

def canonical_dump(source: str) -> str:
    module = ast.parse(source)
    return ast.dump(module, include_attributes=False)


SAMPLE_SOURCE = """
from math import sqrt


def hypotenuse(a: float, b: float) -> float:
    total = a * a + b * b
    return sqrt(total)
""".strip()


@pytest.mark.parametrize("passphrase", ["seekrit", "longer passphrase"])
def test_roundtrip(passphrase: str) -> None:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    assert stream.dictionary_version == "1.0"
    assert stream.encoder_version == "1.0"
    assert len(stream.tokens) == len(stream.human_readable)
    assert stream.source_map is not None
    assert len(stream.source_map.entries) == len(stream.tokens)
    package = encode_package(stream)
    assert package.compression_backend == "rans"
    assert package.compression_model["precision_bits"] == 12
    assert len(package.string_table_bytes) > 0
    assert package.metadata.source_language == "python"
    assert package.compression_extras is not None
    assert "optimisation" in package.compression_extras
    assert package.payload_channels is not None
    channels = package.payload_channels
    assert channels.entries
    def contains_reference(value: object) -> bool:
        if isinstance(value, dict):
            if "__strref__" in value:
                return True
            return any(contains_reference(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_reference(item) for item in value)
        return False

    assert any(contains_reference(payload["value"]) for payload in package.encoded_payloads)
    string_table = StringTable.from_bytes(package.string_table_bytes)
    assert len(channels.entries) == len(package.payloads)
    if channels.identifier_indices:
        assert max(channels.identifier_indices) < len(string_table)
    payload_bytes = package.to_bytes(passphrase)
    decoded_stream = decode_package(payload_bytes, passphrase)
    assert decoded_stream.dictionary.version == stream.dictionary_version
    assert decoded_stream.source_language == "python"
    expected_hash = hashlib.sha256(SAMPLE_SOURCE.encode("utf-8")).hexdigest()
    assert decoded_stream.source_hash == expected_hash
    assert decoded_stream.source_map is not None
    assert len(decoded_stream.source_map.entries) == len(decoded_stream.tokens)
    decoder = QYNDecoder(
        decoded_stream.dictionary, decoded_stream.tokens, decoded_stream.payloads
    )
    module = decoder.decode()
    regenerated_source = ast.unparse(module)
    assert canonical_dump(SAMPLE_SOURCE) == canonical_dump(regenerated_source)
    assert decoded_stream.payloads == package.payloads


def test_deterministic_dictionary() -> None:
    encoder_a = QYNEncoder()
    stream_a = encoder_a.encode(SAMPLE_SOURCE)
    encoder_b = QYNEncoder()
    stream_b = encoder_b.encode(SAMPLE_SOURCE)
    assert stream_a.tokens == stream_b.tokens
    assert [p.__dict__ for p in stream_a.payloads] == [p.__dict__ for p in stream_b.payloads]
    assert stream_a.dictionary_version == stream_b.dictionary_version


def test_wrong_passphrase_rejected() -> None:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    package = encode_package(stream)
    payload_bytes = package.to_bytes("seekrit")
    with pytest.raises(ValueError):
        decode_package(payload_bytes, "otherpass")


def test_metadata_tampering_detected() -> None:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    package = encode_package(stream)
    payload_bytes = package.to_bytes("seekrit")
    frame, remainder = read_frame(payload_bytes, expected_magic=package_module.WRAPPER_MAGIC)
    assert not remainder
    wrapper = json.loads(frame.body.decode("utf-8"))
    wrapper["metadata"]["dictionary_version"] = "2.0"
    tampered_body = json.dumps(wrapper, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    tampered = write_frame(
        magic=package_module.WRAPPER_MAGIC,
        version=frame.version,
        features=frame.features,
        body=tampered_body,
    )
    structured, version, wrapper, remainder = _extract_wrapper_components(payload_bytes)
    wrapper["metadata"]["dictionary_version"] = "2.0"
    tampered = _assemble_wrapper_components(structured, version, wrapper, remainder)
    with pytest.raises(ValueError):
        decode_package(tampered, "seekrit")
    if not structured:
        wrapper = json.loads(payload_bytes.decode("utf-8"))
        wrapper["metadata"]["dictionary_version"] = "2.0"
        tampered = json.dumps(wrapper).encode("utf-8")
        with pytest.raises(ValueError):
            decode_package(tampered, "seekrit")


def test_compression_modes_metadata() -> None:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    maximum_plan = build_frequency_plan(stream.tokens)
    maximum = encode_package(
        stream,
        compression=get_compression_config("maximum"),
        token_plan=maximum_plan,
    )
    assert maximum.compression_extras is not None
    assert maximum.compression_extras.get("mode") == "maximum"
    assert "optimisation" in maximum.compression_extras
    secure = encode_package(stream, compression=get_compression_config("security"))
    assert secure.compression_extras is not None
    assert secure.compression_extras.get("mode") == "security"
    assert "optimisation" not in secure.compression_extras
    decoded = decode_package(maximum.to_bytes("secret"), "secret")
    assert len(decoded.tokens) == len(stream.tokens)


def test_dictionary_has_minimum_entries() -> None:
    dictionary = load_dictionary()
    assert len(dictionary.entries) >= 200


def test_human_readable_tokens_match_dictionary() -> None:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    for token_index, token_key in zip(stream.tokens, stream.human_readable):
        entry = stream.dictionary.entry_for_index(token_index)
        assert entry.morpheme in token_key
        assert entry.key in token_key


def test_available_backends_reports_rans() -> None:
    backends = available_backends()
    assert "rans" in backends
    assert backends["rans"] == "available"


