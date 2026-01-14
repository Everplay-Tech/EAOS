import json
import subprocess
import sys
from pathlib import Path

from qyn1 import QYNEncoder, encode_package


def _write_package(path: Path, source: str, passphrase: str = "pw") -> None:
    stream = QYNEncoder().encode(source)
    package = encode_package(stream)
    path.write_bytes(package.to_bytes(passphrase))


def test_cli_inspect(tmp_path):
    package_path = tmp_path / "sample.qyn1"
    _write_package(
        package_path,
        """
from math import sqrt


def hypotenuse(a: float, b: float) -> float:
    return sqrt(a * a + b * b)
""".strip(),
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "inspect",
            str(package_path),
            "--json",
            "--show-metadata",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    assert data["metadata"]["symbol_count"] > 0


def test_cli_source_map_and_morphemes(tmp_path):
    package_path = tmp_path / "sample.qyn1"
    map_path = tmp_path / "sample.map"
    _write_package(package_path, "def example(x):\n    return x + 1\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "source-map",
            str(package_path),
            "--passphrase",
            "pw",
            "--json",
            "--output",
            str(map_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)
    assert summary["available"] is True
    assert map_path.exists()
    morphemes = subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "morphemes",
            str(package_path),
            "--passphrase",
            "pw",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "meta:stream_start" in morphemes.stdout


def test_cli_diff_and_lint(tmp_path):
    package_a = tmp_path / "a.qyn1"
    package_b = tmp_path / "b.qyn1"
    _write_package(package_a, "def add(a, b):\n    return a + b\n")
    _write_package(package_b, "def add(a, b):\n    total = a + b\n    return total\n")
    diff_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "diff",
            str(package_a),
            str(package_b),
            "--passphrase",
            "pw",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    diff_data = json.loads(diff_result.stdout)
    assert isinstance(diff_data["token_differences"], list)
    lint_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "lint",
            str(package_a),
            "--passphrase",
            "pw",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "OK" in lint_result.stdout
