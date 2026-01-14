from dataclasses import replace

from qyn1.compression_config import get_compression_config
from qyn1.encoder import QYNEncoder
from qyn1.package import decode_package, encode_package


PASS = "test-passphrase"


def _roundtrip_source(mode: str) -> None:
    encoder = QYNEncoder()
    stream = encoder.encode("x = 1\n")
    base_config = get_compression_config(None)
    config = replace(base_config, backend="rans", backend_options={}, model_mode=mode)
    package = encode_package(stream, backend_name="rans", compression=config, model_mode=mode)
    recovered = decode_package(package.to_bytes(PASS), PASS)
    assert list(recovered.tokens) == list(stream.tokens)


def test_static_mode_roundtrip():
    _roundtrip_source("static")


def test_hybrid_mode_roundtrip_and_metadata():
    encoder = QYNEncoder()
    stream = encoder.encode("x = 2\ny = x + 3\n")
    base_config = get_compression_config(None)
    config = replace(base_config, backend="rans", backend_options={}, model_mode="hybrid")
    package = encode_package(stream, backend_name="rans", compression=config, model_mode="hybrid")
    assert package.compression_model.get("mode") == "hybrid"
    assert "overrides" in package.compression_model
    recovered = decode_package(package.to_bytes(PASS), PASS)
    assert list(recovered.tokens) == list(stream.tokens)
