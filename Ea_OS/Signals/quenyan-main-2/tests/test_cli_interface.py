import json
import json
import subprocess
import sys


def test_cli_encode_verify_completion(tmp_path) -> None:
    source = tmp_path / "module.py"
    source.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    key_file = tmp_path / "key.txt"
    key_file.write_text("secret\n", encoding="utf-8")
    package = tmp_path / "module.qyn1"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "encode",
            str(source),
            "-o",
            str(package),
            "--key",
            str(key_file),
            "--quiet",
        ],
        check=True,
    )
    assert package.exists()

    verify = subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "verify",
            str(package),
            "--key",
            str(key_file),
            "--check-signature",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(verify.stdout)
    assert payload["status"] == "ok"
    assert payload["symbol_count"] > 0

    completion = subprocess.run(
        [sys.executable, "-m", "qyn1.cli", "completion", "bash"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "complete -F" in completion.stdout


def test_cli_init_and_man(tmp_path) -> None:
    workspace = tmp_path / "project"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "init",
            str(workspace),
            "--generate-keys",
        ],
        check=True,
    )
    config = workspace / ".quenyan" / "config.json"
    key = workspace / ".quenyan" / "keys" / "master.key"
    assert config.exists()
    assert key.exists()
    man_page = subprocess.run(
        [sys.executable, "-m", "qyn1.cli", "man"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "QUENYAN" in man_page.stdout


def test_cli_migrate(tmp_path) -> None:
    source = tmp_path / "module.py"
    source.write_text("def foo(x):\n    return x * 2\n", encoding="utf-8")
    key_file = tmp_path / "key.txt"
    key_file.write_text("secret\n", encoding="utf-8")
    package = tmp_path / "module.qyn1"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "encode",
            str(source),
            "--key",
            str(key_file),
            "--quiet",
        ],
        check=True,
    )
    migrated = tmp_path / "module.upgraded.qyn1"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "migrate",
            str(package),
            "--output",
            str(migrated),
            "--key",
            str(key_file),
            "--target-package",
            "1.1.0",
            "--quiet",
        ],
        check=True,
    )
    assert migrated.exists()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "qyn1.cli",
            "migrate",
            str(migrated),
            "--key",
            str(key_file),
        ],
        check=True,
    )
    backup = migrated.with_suffix(migrated.suffix + ".bak")
    assert backup.exists()
