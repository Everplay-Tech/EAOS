import ast

from qyn1.encoder import QYNEncoder
from qyn1.decoder import QYNDecoder


def test_decoder_uses_channelised_payloads() -> None:
    source = """
def foo(x):
    return x
"""
    encoder = QYNEncoder()
    stream = encoder.encode(source)

    decoder = QYNDecoder(
        stream.dictionary,
        list(stream.tokens),
        [],
        payload_channels=stream.payload_channels,
    )
    module = decoder.decode()

    expected = ast.parse(source)
    assert ast.dump(module, include_attributes=False) == ast.dump(
        expected, include_attributes=False
    )
