import ast
import json
from pathlib import Path
from typing import Iterable

import pytest

from qyn1 import QYNDecoder, QYNEncoder, decode_package, encode_package
from qyn1.compression import decompress_bytes
from qyn1.package import decode_stream, read_package
from qyn1.token_optimisation import TokenOptimisationPlan

FIXTURE_ROOT = Path(__file__).parent / "data" / "corpus"


def _iter_fixture_sources() -> Iterable[tuple[str, str, str]]:
    manifest = json.loads((FIXTURE_ROOT / "fixtures.json").read_text("utf-8"))
    for entry in manifest:
        language = entry["language"]
        version = entry["version"]
        path = FIXTURE_ROOT / entry["path"]
        yield language, version, path.read_text("utf-8")


def _canonical_ast(source: str) -> str:
    return ast.dump(ast.parse(source), include_attributes=False)


@pytest.mark.parametrize("passphrase", ["integration-pass", "longer-secret"])
def test_corpus_round_trip(passphrase: str) -> None:
    encoder = QYNEncoder()
    for language, version, source in _iter_fixture_sources():
        stream = encoder.encode(source)
        package = encode_package(stream)
        payload = package.to_bytes(passphrase)
        decoded = decode_package(payload, passphrase)
        assert decoded.source_language == package.metadata.source_language
        assert decoded.source_language_version == package.metadata.source_language_version
        assert decoded.dictionary.version == stream.dictionary.version
        assert decoded.source_map is not None
        decoder = QYNDecoder(decoded.dictionary, decoded.tokens, decoded.payloads)
        module = decoder.decode()
        regenerated = ast.unparse(module)
        assert decoded.source_hash == stream.source_hash
        decoded_stream = read_package(payload, passphrase)
        assert decoded_stream.metadata.source_language == package.metadata.source_language
        assert decoded_stream.metadata.symbol_count == len(decoded.tokens)
        stream_info = decode_stream(decoded_stream.payload)
        roundtrip = decompress_bytes(
            stream_info["compression"]["backend"],
            stream_info["compression"]["model"],
            stream_info["compression"]["payload"],
            stream_info["compression"]["symbol_count"],
        )
        optimisation = stream_info["compression"].get("optimisation")
        if isinstance(optimisation, dict):
            roundtrip = TokenOptimisationPlan.from_metadata(optimisation).restore(roundtrip)
        assert roundtrip == decoded.tokens


@pytest.mark.parametrize("passphrase", ["integration-pass"])
def test_metadata_consistency_under_load(passphrase: str) -> None:
    encoder = QYNEncoder()
    accumulated = []
    for _, _, source in _iter_fixture_sources():
        stream = encoder.encode(source)
        package = encode_package(stream)
        payload = package.to_bytes(passphrase)
        recorded = read_package(payload, passphrase)
        accumulated.append(recorded.metadata)
    languages = {meta.source_language for meta in accumulated}
    assert languages == {"python"}
    counts = {meta.symbol_count for meta in accumulated}
    assert all(count > 0 for count in counts)
