from __future__ import annotations

import json
import subprocess
import json
import subprocess
import sys

from qyn1.compression import ChunkedRANSBackend
from qyn1.compression_config import get_compression_config
from qyn1.decoder import QYNDecoder
from qyn1.encoder import QYNEncoder
from qyn1.pipeline import encode_project
import qyn1.package as package_module
from qyn1.format import read_frame
from qyn1.package import decode_package
from qyn1.streaming import ChunkedTokenBuffer, NullCollector


def test_chunked_backend_round_trip(tmp_path) -> None:
    encoder = QYNEncoder()
    source = """
def add(a: int, b: int) -> int:
    return a + b
""".strip()
    stream = encoder.encode(source)
    backend = ChunkedRANSBackend(chunk_size=4)
    model = backend.build_model(stream.tokens, len(stream.dictionary))
    compressed = backend.encode(stream.tokens, model)
    decoded = backend.decode(compressed, model, len(stream.tokens))
    assert list(stream.tokens) == decoded


def test_chunked_backend_with_streaming_buffer(tmp_path) -> None:
    encoder = QYNEncoder()
    source = """
def fib(n: int) -> int:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)
""".strip()
    buffer = ChunkedTokenBuffer(chunk_size=3, max_buffered_tokens=3)
    stream = encoder.encode(source, token_buffer=buffer, human_buffer=NullCollector())
    buffer.close()
    backend = ChunkedRANSBackend(chunk_size=3)
    model = backend.build_model(buffer, len(stream.dictionary))
    compressed = backend.encode(buffer, model)
    decoded = backend.decode(compressed, model, len(buffer))
    assert list(buffer.iter_tokens()) == decoded
    buffer.dispose()


def test_encode_project_parallel(tmp_path) -> None:
    sample_a = tmp_path / "a.py"
    sample_b = tmp_path / "b.py"
    sample_a.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    sample_b.write_text("def beta():\n    return 2\n", encoding="utf-8")
    output_dir = tmp_path / "packages"
    report = encode_project(
        [sample_a, sample_b],
        output_dir,
        "passphrase",
        max_workers=2,
        streaming_threshold=0,
        chunk_size=8,
        max_buffered_tokens=8,
    )
    assert len(report.results) == 2
    for result in report.results:
        assert result.output.exists()
        stream = decode_package(result.output.read_bytes(), "passphrase")
        decoder = QYNDecoder(stream.dictionary, list(stream.tokens), stream.payloads)
        module = decoder.decode()
        assert module.body


def test_encode_project_shared_dictionary(tmp_path) -> None:
    sources = []
    for name, body in {
        "alpha.py": "def alpha(value):\n    return value + 1\n",
        "beta.py": "def beta(value):\n    return value + 2\n",
        "gamma.py": "def gamma(value):\n    return value + 3\n",
    }.items():
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        sources.append(path)
    output_dir = tmp_path / "archive"
    config = get_compression_config("maximum")
    report = encode_project(
        sources,
        output_dir,
        "passphrase",
        compression_config=config,
    )
    assert len(report.results) == len(sources)
    assert all(not item.streaming for item in report.results)
    for result in report.results:
        frame, remainder = read_frame(
            result.output.read_bytes(), expected_magic=package_module.WRAPPER_MAGIC
        )
        assert not remainder
        wrapper = json.loads(frame.body.decode("utf-8"))
        assert wrapper["metadata"]["compression_backend"] == config.backend
        stream = decode_package(result.output.read_bytes(), "passphrase")
        decoder = QYNDecoder(stream.dictionary, list(stream.tokens), stream.payloads)
        module = decoder.decode()
        assert module.body


def test_cli_encode_project(tmp_path) -> None:
    package_dir = tmp_path / "out"
    package_dir.mkdir()
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 'ok'\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "encode-project",
            str(package_dir),
            str(source),
            "--passphrase",
            "secret",
            "--streaming-threshold",
            "0",
            "--chunk-size",
            "4",
            "--max-buffered-tokens",
            "4",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["files"]
    output_path = package_dir / "main.qyn1"
    assert output_path.exists()
    stream = decode_package(output_path.read_bytes(), "secret")
    decoder = QYNDecoder(stream.dictionary, list(stream.tokens), stream.payloads)
    module = decoder.decode()
    assert module.body
