import ast

from qyn1 import QYNEncoder, decode_package, encode_package
from qyn1.source_map import SourceMap


def test_source_map_entries_align():
    source = """
import math


def compute(x: float) -> float:
    return math.sqrt(x)
""".strip()
    encoder = QYNEncoder()
    stream = encoder.encode(source)
    assert stream.source_map is not None
    entries = stream.source_map.entries
    assert all(entry.token_index == index for index, entry in enumerate(entries))
    package = encode_package(stream)
    package_bytes = package.to_bytes("secret")
    decoded = decode_package(package_bytes, "secret")
    assert decoded.source_map is not None
    # round trip through bytes
    assert SourceMap.from_bytes(decoded.source_map.to_bytes()).to_dict() == decoded.source_map.to_dict()
    module = ast.parse(source)
    assert module.body[0].lineno == 1
