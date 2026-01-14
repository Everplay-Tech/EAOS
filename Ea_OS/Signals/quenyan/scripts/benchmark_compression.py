"""Benchmark compression backends and string table packing."""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qyn1.compression import OptionalBackendUnavailable, available_backends, get_backend
from qyn1.encoder import QYNEncoder
from qyn1.string_table import StringTable

SAMPLE_SOURCE = """
from math import sqrt


def hypotenuse(a: float, b: float) -> float:
    total = a * a + b * b
    return sqrt(total)
""".strip()


@dataclass
class BackendBenchmark:
    name: str
    status: str
    model_build_time_us: float | None = None
    encode_time_us: float | None = None
    decode_time_us: float | None = None
    compressed_size: int | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "model_build_time_us": self.model_build_time_us,
            "encode_time_us": self.encode_time_us,
            "decode_time_us": self.decode_time_us,
            "compressed_size": self.compressed_size,
        }


def time_callable(func, iterations: int = 25) -> float:
    samples: List[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        samples.append((time.perf_counter() - start) * 1_000_000)
    return statistics.median(samples)


def benchmark_backends(stream) -> List[BackendBenchmark]:
    results: List[BackendBenchmark] = []
    statuses = available_backends()
    for name in statuses:
        status = statuses[name]
        if status != "available":
            results.append(BackendBenchmark(name=name, status=status))
            continue
        try:
            backend = get_backend(name)
        except OptionalBackendUnavailable as exc:  # pragma: no cover - sanity guard
            results.append(BackendBenchmark(name=name, status=str(exc)))
            continue
        model_build_time = time_callable(
            lambda: backend.build_model(stream.tokens, len(stream.dictionary)), iterations=10
        )
        model = backend.build_model(stream.tokens, len(stream.dictionary))
        compressed = backend.encode(stream.tokens, model)
        encode_time = time_callable(lambda: backend.encode(stream.tokens, model))
        decode_time = time_callable(lambda: backend.decode(compressed, model, len(stream.tokens)))
        decoded = backend.decode(compressed, model, len(stream.tokens))
        if decoded != stream.tokens:
            results.append(BackendBenchmark(name=name, status="mismatch"))
            continue
        results.append(
            BackendBenchmark(
                name=name,
                status="ok",
                model_build_time_us=model_build_time,
                encode_time_us=encode_time,
                decode_time_us=decode_time,
                compressed_size=len(compressed),
            )
        )
    return results


def analyse_string_table(stream) -> Dict[str, Any]:
    string_table = StringTable.build_from_payloads(stream.payloads)
    encoded_payloads = [string_table.encode_payload(payload) for payload in stream.payloads]
    raw_payload_bytes = len(json.dumps([payload.__dict__ for payload in stream.payloads]).encode("utf-8"))
    encoded_payload_bytes = len(json.dumps(encoded_payloads).encode("utf-8"))
    string_table_bytes = len(string_table.to_bytes())
    deduplicated_bytes = encoded_payload_bytes + string_table_bytes
    return {
        "raw_payload_bytes": raw_payload_bytes,
        "encoded_payload_bytes": encoded_payload_bytes,
        "string_table_bytes": string_table_bytes,
        "deduplicated_bytes": deduplicated_bytes,
        "savings_bytes": raw_payload_bytes - deduplicated_bytes,
    }


def main() -> None:
    encoder = QYNEncoder()
    stream = encoder.encode(SAMPLE_SOURCE)
    backend_results = [result.to_dict() for result in benchmark_backends(stream)]
    payload_analysis = analyse_string_table(stream)
    summary = {
        "sample_loc": SAMPLE_SOURCE.count("\n") + 1,
        "token_count": len(stream.tokens),
        "backends": backend_results,
        "string_table": payload_analysis,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
