from __future__ import annotations

from pathlib import Path

import argparse
import pytest

import qyn1.cli as cli
from qyn1.encoder import QYNEncoder
from qyn1.dictionary import MorphemeDictionary, UnknownMorphemeError, load_dictionary
from qyn1.migration import migrate_bytes
from qyn1.package import decode_package, encode_package
from qyn1.repository import RepositoryWriter, diff_repository_indexes
from qyn1.versioning import CURRENT_PACKAGE_VERSION


def _encode_sample(body: str, passphrase: str) -> bytes:
    encoder = QYNEncoder()
    stream = encoder.encode(body)
    package = encode_package(stream)
    return package.to_bytes(passphrase)

def _dictionary_without_return(strict: bool = False) -> MorphemeDictionary:
    base = load_dictionary()
    entries = [entry for entry in base.entries if entry.key != "flow:return"]
    return MorphemeDictionary(base.version, entries, strict_morpheme_errors=strict)


def test_migrate_bytes_updates_versions() -> None:
    passphrase = "secret"
    original = _encode_sample("def add(a, b):\n    return a + b\n", passphrase)
    upgraded, report = migrate_bytes(
        original,
        passphrase,
        target_dictionary="1.1.0",
        target_package_version="1.1.0",
    )
    assert report.package_version == "1.1.0"
    assert report.dictionary_version == "1.1"

    upgraded_stream = decode_package(upgraded, passphrase)
    assert upgraded_stream.dictionary.version == "1.1"

    rolled_back, rollback_report = migrate_bytes(
        upgraded,
        passphrase,
        target_dictionary="1.0",
        target_package_version=CURRENT_PACKAGE_VERSION.text,
    )
    rolled_stream = decode_package(rolled_back, passphrase)
    assert rolled_stream.dictionary.version == "1.0"
    assert rollback_report.package_version == CURRENT_PACKAGE_VERSION.text


def test_migrate_bytes_strict_errors_on_missing_morphemes(monkeypatch) -> None:
    passphrase = "secret"
    original = _encode_sample("def foo(x):\n    return x + 1\n", passphrase)

    missing_return = _dictionary_without_return(strict=True)
    monkeypatch.setattr(
        "qyn1.migration.load_dictionary",
        lambda version="1.0", strict_morpheme_errors=False: missing_return,
    )

    with pytest.raises(UnknownMorphemeError):
        migrate_bytes(original, passphrase, strict_morpheme_errors=True)


def test_migrate_bytes_rejects_incompatible_dictionary_version() -> None:
    passphrase = "secret"
    original = _encode_sample("def foo(x):\n    return x + 1\n", passphrase)
    with pytest.raises(ValueError) as excinfo:
        migrate_bytes(original, passphrase, target_dictionary="9.9")
    assert "dictionary version 9.9" in str(excinfo.value).lower()


def test_migrate_changes_repository_hashes(tmp_path: Path) -> None:
    passphrase = "secret"
    root = tmp_path / "src"
    root.mkdir()
    src_a = root / "a.py"
    src_a.write_text("def a(x):\n    return x * 2\n", encoding="utf-8")
    src_b = root / "b.py"
    src_b.write_text("def b(x):\n    return x - 1\n", encoding="utf-8")

    package_a = _encode_sample(src_a.read_text(encoding="utf-8"), passphrase)
    package_b = _encode_sample(src_b.read_text(encoding="utf-8"), passphrase)

    repo_before_dir = tmp_path / "repo_before"
    writer_before = RepositoryWriter(
        root, repo_before_dir, compression_mode="balanced", backend="rans"
    )
    writer_before.add_package(src_a, package_a)
    writer_before.add_package(src_b, package_b)
    index_before = writer_before.finalise()

    migrated_a, _ = migrate_bytes(package_a, passphrase, target_package_version="1.1.0")
    assert migrated_a != package_a

    repo_after_dir = tmp_path / "repo_after"
    writer_after = RepositoryWriter(
        root, repo_after_dir, compression_mode="balanced", backend="rans"
    )
    writer_after.add_package(src_a, migrated_a)
    writer_after.add_package(src_b, package_b)
    index_after = writer_after.finalise()

    diff = diff_repository_indexes(index_after, index_before)
    assert diff["changed"] == ["a.py"]
    assert diff["added"] == []
    assert diff["removed"] == []


def test_cli_migrate_surfaces_strict_morpheme_errors(tmp_path, monkeypatch) -> None:
    source = tmp_path / "module.py"
    source.write_text("def foo(x):\n    return x + 1\n", encoding="utf-8")
    key_file = tmp_path / "key.txt"
    key_file.write_text("secret\n", encoding="utf-8")
    package = tmp_path / "module.qyn1"

    encoder = QYNEncoder()
    stream = encoder.encode(source.read_text(encoding="utf-8"))
    package.write_bytes(encode_package(stream).to_bytes("secret"))

    missing_return = _dictionary_without_return(strict=True)
    monkeypatch.setattr(
        "qyn1.migration.load_dictionary",
        lambda version="1.0", strict_morpheme_errors=False: missing_return,
    )

    args = argparse.Namespace(
        package=str(package),
        output=None,
        target_dictionary="1.0",
        target_package=None,
        key=str(key_file),
        passphrase=None,
        no_backup=True,
        quiet=True,
        strict_morpheme_errors=True,
    )
    with pytest.raises(cli.CommandError):
        cli.migrate_command(args)


def test_cli_migrate_reports_incompatible_dictionary(tmp_path) -> None:
    source = tmp_path / "module.py"
    source.write_text("def foo(x):\n    return x + 1\n", encoding="utf-8")
    key_file = tmp_path / "key.txt"
    key_file.write_text("secret\n", encoding="utf-8")
    package = tmp_path / "module.qyn1"

    encoder = QYNEncoder()
    stream = encoder.encode(source.read_text(encoding="utf-8"))
    package.write_bytes(encode_package(stream).to_bytes("secret"))

    args = argparse.Namespace(
        package=str(package),
        output=None,
        target_dictionary="9.9",
        target_package=None,
        key=str(key_file),
        passphrase=None,
        no_backup=True,
        quiet=True,
        strict_morpheme_errors=False,
    )
    with pytest.raises(cli.CommandError) as excinfo:
        cli.migrate_command(args)
    assert "dictionary version 9.9" in str(excinfo.value).lower()
