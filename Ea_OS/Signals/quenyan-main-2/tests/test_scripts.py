import json
import subprocess
import sys
from pathlib import Path


def test_profile_morphemes_script(tmp_path) -> None:
    sample_dir = tmp_path / "sample"
    sample_dir.mkdir()
    (sample_dir / "example.py").write_text(
        """
from typing import Any


def identity(value: Any) -> Any:
    return value
""".strip(),
        encoding="utf-8",
    )
    output = tmp_path / "profile.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "profile_morphemes.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--input",
            f"python={sample_dir}",
            "--output",
            str(output),
        ],
        check=True,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert "python" in data["languages"]
    assert data["languages"]["python"]["token_count"] > 0
    assert data["languages"]["python"]["conditional_entropy_bits"] >= 0.0


def test_benchmark_compression_script_runs() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_compression.py"
    result = subprocess.run([sys.executable, str(script)], check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    assert "backends" in data
    assert any(entry["name"] == "rans" for entry in data["backends"])
