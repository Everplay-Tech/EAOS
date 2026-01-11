import binascii
import json
import struct

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st  # type: ignore

from qyn1.compression import ANSCompressionError, decompress_bytes
from qyn1.package import decode_stream, read_package

pytestmark = pytest.mark.property


@given(st.binary(min_size=1), st.text())
@settings(max_examples=50)
def test_read_package_fuzzer(data: bytes, passphrase: str) -> None:
    try:
        read_package(data, passphrase or "default")
        pytest.fail("unexpectedly decoded arbitrary data")
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
        pass


@given(st.binary(min_size=1))
@settings(max_examples=50)
def test_decode_stream_fuzzer(data: bytes) -> None:
    with pytest.raises((ValueError, json.JSONDecodeError, UnicodeDecodeError, struct.error)):
        decode_stream(data)


@given(st.binary(min_size=1), st.integers(min_value=0, max_value=16))
@settings(max_examples=50)
def test_decompress_bytes_fuzzer(data: bytes, symbol_count: int) -> None:
    model = {"precision_bits": 12, "frequencies": [1, 1, 1, 1]}
    try:
        decompress_bytes("rans", model, data, symbol_count)
    except (ValueError, RuntimeError, ANSCompressionError):
        pass
