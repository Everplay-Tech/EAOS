import base64

import pytest

from qyn1 import QYNEncoder, decode_package, encode_package
from qyn1.package import decode_stream, read_package, _assemble_wrapper_components, _extract_wrapper_components

SAMPLE_SOURCE = "print('nonce')\n"


@pytest.mark.parametrize("passphrase", ["hazard-fence"])
def test_nonce_reuse_ciphertext_swap_detected(passphrase: str) -> None:
    encoder = QYNEncoder()
    stream_a = encoder.encode(SAMPLE_SOURCE)
    package_a = encode_package(stream_a)
    stream_b = encoder.encode("print('other')\n")
    package_b = encode_package(stream_b)
    payload_a = package_a.to_bytes(passphrase)
    payload_b = package_b.to_bytes(passphrase)
    structured_a, version_a, wrapper_a, remainder_a = _extract_wrapper_components(payload_a)
    structured_b, _, wrapper_b, remainder_b = _extract_wrapper_components(payload_b)
    assert structured_a and structured_b
    assert not remainder_a and not remainder_b
    wrapper_a["nonce"] = wrapper_b["nonce"]
    wrapper_a["ciphertext"] = wrapper_b["ciphertext"]
    wrapper_a["tag"] = wrapper_b["tag"]
    tampered = _assemble_wrapper_components(structured_a, version_a, wrapper_a, b"")
    with pytest.raises(ValueError):
        decode_package(tampered, passphrase)


@pytest.mark.parametrize("passphrase", ["hazard-fence"])
def test_truncated_wrapper_detected(passphrase: str) -> None:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    package = encode_package(stream)
    payload = package.to_bytes(passphrase)
    truncated = payload[:-8]
    with pytest.raises(ValueError):
        read_package(truncated, passphrase)


@pytest.mark.parametrize("passphrase", ["hazard-fence"])
def test_corrupted_stream_metadata_rejected(passphrase: str) -> None:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    package = encode_package(stream)
    payload = package.to_bytes(passphrase)
    envelope = read_package(payload, passphrase)
    corrupted = bytearray(envelope.payload)
    if corrupted:
        corrupted[-1] ^= 0xFF
    structured, version, wrapper, _ = _extract_wrapper_components(payload)
    assert structured
    wrapper["ciphertext"] = base64.b64encode(corrupted).decode("ascii")
    tampered = _assemble_wrapper_components(True, version, wrapper, b"")
    with pytest.raises(ValueError):
        decode_package(tampered, passphrase)
    with pytest.raises(ValueError):
        decode_stream(bytes(corrupted))
