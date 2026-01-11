import json
from pathlib import Path

import pytest

from qyn1.benchmarks import UnsupportedLanguageError, benchmark_dataset, load_manifest
from scripts import run_benchmark_suite


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(Path("data/benchmark_suite_manifest.json"))


def test_manifest_contains_fixture(manifest) -> None:
    slug_map = {entry.slug: entry for entry in manifest}
    assert "python-small-flask" in slug_map
    descriptor = slug_map["python-small-flask"]
    assert descriptor.local_fixture == "tests/data/benchmarks/python_small"
    assert descriptor.language == "python"


def test_benchmark_fixture_dataset(tmp_path, manifest) -> None:
    slug_map = {entry.slug: entry for entry in manifest}
    descriptor = slug_map["python-small-flask"]
    summary = benchmark_dataset(
        descriptor,
        workspace=tmp_path / "workspace",
        output_dir=tmp_path / "output",
        passphrase="test-passphrase",
    )
    assert summary.total_input_bytes > 0
    assert summary.total_encoded_bytes > 0
    assert summary.encode_seconds >= 0
    assert summary.total_overhead_bytes >= 0


def test_benchmark_suite_cli_skip_unsupported(tmp_path, manifest) -> None:
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    results_path = tmp_path / "results.json"
    code = run_benchmark_suite.main(
        [
            str(workspace),
            str(output),
            "--results",
            str(results_path),
            "--datasets",
            "python-small-flask",
            "javascript-small-astro",
        ]
    )
    assert code == 0
    payload = json.loads(results_path.read_text())
    assert len(payload["results"]) == 1
    assert payload["results"][0]["slug"] == "python-small-flask"
    assert payload["skipped"] and payload["skipped"][0]["slug"] == "javascript-small-astro"


def test_strict_mode_raises(tmp_path, manifest) -> None:
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    with pytest.raises(UnsupportedLanguageError):
        run_benchmark_suite.main(
            [
                str(workspace),
                str(output),
                "--datasets",
                "javascript-small-astro",
                "--strict",
            ]
        )
