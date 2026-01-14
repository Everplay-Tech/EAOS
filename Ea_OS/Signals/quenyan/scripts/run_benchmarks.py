"""Benchmark QYN-1 morpheme encoding against alternative serialisations."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import marshal
import statistics
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from qyn1.decoder import QYNDecoder
from qyn1.encoder import QYNEncoder

SAMPLE_SOURCE = """
from math import sqrt


def hypotenuse(a: float, b: float) -> float:
    total = a * a + b * b
    return sqrt(total)
""".strip()


@dataclass
class BenchmarkResult:
    name: str
    encode_time_us: float
    decode_time_us: float
    size_bytes: int
    deterministic: bool


# ---------------------------------------------------------------------------
# Helper serialisers


def ast_to_dict(node: Any) -> Any:
    if isinstance(node, ast.AST):
        result: Dict[str, Any] = {"_type": type(node).__name__}
        for field, value in ast.iter_fields(node):
            result[field] = ast_to_dict(value)
        return result
    if isinstance(node, list):
        return [ast_to_dict(item) for item in node]
    return node


def dict_to_ast(data: Any) -> Any:
    if isinstance(data, dict) and "_type" in data:
        node_type = getattr(ast, data["_type"])
        kwargs = {key: dict_to_ast(value) for key, value in data.items() if key != "_type"}
        return node_type(**kwargs)
    if isinstance(data, list):
        return [dict_to_ast(item) for item in data]
    return data


def ast_to_sexpr(node: Any) -> Any:
    if isinstance(node, ast.AST):
        children = []
        for field, value in ast.iter_fields(node):
            children.append([field, ast_to_sexpr(value)])
        return [type(node).__name__, children]
    if isinstance(node, list):
        return [ast_to_sexpr(item) for item in node]
    return node


def sexpr_to_ast(data: Any) -> Any:
    if isinstance(data, list) and data and isinstance(data[0], str):
        node_type = getattr(ast, data[0])
        kwargs = {field: sexpr_to_ast(value) for field, value in data[1]}
        return node_type(**kwargs)
    if isinstance(data, list):
        return [sexpr_to_ast(item) for item in data]
    return data


# ---------------------------------------------------------------------------
# Benchmark harness


def time_callable(func) -> float:
    samples: List[float] = []
    for _ in range(10):
        start = time.perf_counter()
        func()
        samples.append((time.perf_counter() - start) * 1_000_000)
    return statistics.median(samples)


def benchmark_morpheme() -> BenchmarkResult:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    size_bytes = len(json.dumps(stream.tokens).encode("utf-8"))
    encode_time = time_callable(lambda: encoder.encode(SAMPLE_SOURCE))

    def decode_once() -> None:
        decoder = QYNDecoder(stream.dictionary, stream.tokens, stream.payloads)
        decoder.decode()

    decode_time = time_callable(decode_once)
    deterministic = True
    for _ in range(5):
        other = encoder.encode(SAMPLE_SOURCE)
        if other.tokens != stream.tokens or other.payloads != stream.payloads:
            deterministic = False
            break
    return BenchmarkResult(
        name="Quenya Morpheme",
        encode_time_us=encode_time,
        decode_time_us=decode_time,
        size_bytes=size_bytes,
        deterministic=deterministic,
    )


def benchmark_proto() -> BenchmarkResult:
    module = ast.parse(SAMPLE_SOURCE)

    def encode() -> bytes:
        return json.dumps(ast_to_dict(module)).encode("utf-8")

    payload = encode()
    encode_time = time_callable(encode)

    def decode() -> ast.AST:
        return dict_to_ast(json.loads(payload))

    decode_time = time_callable(decode)
    deterministic = payload == encode()
    return BenchmarkResult(
        name="AST Dict (Proto-like)",
        encode_time_us=encode_time,
        decode_time_us=decode_time,
        size_bytes=len(payload),
        deterministic=deterministic,
    )


def benchmark_opcode() -> BenchmarkResult:
    code_obj = compile(SAMPLE_SOURCE, "<bench>", "exec")

    def encode() -> bytes:
        return marshal.dumps(code_obj)

    payload = encode()
    encode_time = time_callable(encode)

    def decode() -> Any:
        return marshal.loads(payload)

    decode_time = time_callable(decode)
    deterministic = payload == encode()
    return BenchmarkResult(
        name="Opcode (marshal)",
        encode_time_us=encode_time,
        decode_time_us=decode_time,
        size_bytes=len(payload),
        deterministic=deterministic,
    )


def benchmark_sexpr() -> BenchmarkResult:
    module = ast.parse(SAMPLE_SOURCE)

    def encode() -> bytes:
        return json.dumps(ast_to_sexpr(module)).encode("utf-8")

    payload = encode()
    encode_time = time_callable(encode)

    def decode() -> ast.AST:
        return sexpr_to_ast(json.loads(payload))

    decode_time = time_callable(decode)
    deterministic = payload == encode()
    return BenchmarkResult(
        name="S-expression JSON",
        encode_time_us=encode_time,
        decode_time_us=decode_time,
        size_bytes=len(payload),
        deterministic=deterministic,
    )


def main() -> None:
    results = [
        benchmark_morpheme(),
        benchmark_proto(),
        benchmark_opcode(),
        benchmark_sexpr(),
    ]
    output = {
        "sample_loc": SAMPLE_SOURCE.count("\n") + 1,
        "results": [result.__dict__ for result in results],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
