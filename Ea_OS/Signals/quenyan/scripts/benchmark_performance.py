"""Collect baseline performance measurements for the QYN-1 pipeline."""

from __future__ import annotations

import argparse
import ast
import gzip
import json
import os
import resource
import sys
import time
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qyn1.crypto import encrypt, decrypt
from qyn1.pipeline import encode_project


def measure_python_ast(sample: str, iterations: int = 20) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        ast.parse(sample)
    duration = time.perf_counter() - start
    total_bytes = len(sample.encode("utf-8")) * iterations
    return total_bytes / duration / 1_048_576


def measure_gzip(sample: bytes, iterations: int = 10) -> dict:
    compress_rates = []
    decompress_rates = []
    for _ in range(iterations):
        start = time.perf_counter()
        compressed = gzip.compress(sample)
        compress_duration = time.perf_counter() - start
        compress_rates.append(len(sample) / compress_duration / 1_048_576)

        start = time.perf_counter()
        gzip.decompress(compressed)
        decompress_duration = time.perf_counter() - start
        decompress_rates.append(len(sample) / decompress_duration / 1_048_576)
    return {
        "compress_mb_s": mean(compress_rates),
        "decompress_mb_s": mean(decompress_rates),
        "compressed_size": len(gzip.compress(sample)),
    }


def measure_aead(sample: bytes, iterations: int = 10) -> dict:
    passphrase = "benchmark-passphrase"
    encrypt_rates = []
    decrypt_rates = []
    for _ in range(iterations):
        start = time.perf_counter()
        encrypted = encrypt(sample, passphrase)
        encrypt_duration = time.perf_counter() - start
        encrypt_rates.append(len(sample) / encrypt_duration / 1_048_576)

        start = time.perf_counter()
        decrypt(encrypted, passphrase)
        decrypt_duration = time.perf_counter() - start
        decrypt_rates.append(len(sample) / decrypt_duration / 1_048_576)
    return {
        "encrypt_mb_s": mean(encrypt_rates),
        "decrypt_mb_s": mean(decrypt_rates),
    }


def measure_pipeline(tmp_dir: Path) -> dict:
    sample_source = """
def value(i: int) -> int:
    total = 0
    for j in range(i):
        total += j
    return total
""" * 200
    files = []
    for index in range(4):
        path = tmp_dir / f"sample_{index}.py"
        path.write_text(sample_source, encoding="utf-8")
        files.append(path)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = encode_project(
        files,
        tmp_dir / "packages",
        "benchmark-passphrase",
        max_workers=1,
        streaming_threshold=0,
        chunk_size=16384,
        max_buffered_tokens=16384,
    )
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "file_count": len(report.results),
        "total_duration_s": report.total_duration_s,
        "throughput_mb_s": report.average_throughput_mb_s,
        "average_duration_s": mean(result.duration_s for result in report.results),
        "peak_rss_mb": max(before, after) / 1024,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/performance_baseline.json"))
    args = parser.parse_args()

    tmp_dir = Path(".performance_tmp")
    tmp_dir.mkdir(exist_ok=True)

    python_sample = "\n".join(
        [
            "def f(x: int, y: int) -> int:",
            "    return x * y + (x - y)",
        ]
        * 1024
    )
    python_mb_s = measure_python_ast(python_sample)

    sample_bytes = python_sample.encode("utf-8") * 2
    gzip_metrics = measure_gzip(sample_bytes)
    aead_metrics = measure_aead(sample_bytes)
    pipeline_metrics = measure_pipeline(tmp_dir)

    output = {
        "python_ast_mb_s": python_mb_s,
        "gzip": gzip_metrics,
        "aead": aead_metrics,
        "pipeline": pipeline_metrics,
        "sample_size_bytes": len(sample_bytes),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")

    for item in tmp_dir.glob("**/*"):
        if item.is_file():
            item.unlink()
    for directory in sorted(tmp_dir.glob("**/*"), reverse=True):
        if directory.is_dir():
            directory.rmdir()
    tmp_dir.rmdir()


if __name__ == "__main__":
    main()
