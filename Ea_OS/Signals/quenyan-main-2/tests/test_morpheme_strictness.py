from __future__ import annotations

import argparse
import warnings

import pytest

import qyn1.cli as cli
import qyn1.encoder as encoder_module
from qyn1.dictionary import (
    MorphemeDictionary,
    UnknownMorphemeError,
    UnknownMorphemeWarning,
    load_dictionary,
)
from qyn1.encoder import QYNEncoder


def _dictionary_without_return(strict: bool) -> MorphemeDictionary:
    base = load_dictionary()
    entries = [entry for entry in base.entries if entry.key != "flow:return"]
    return MorphemeDictionary(base.version, entries, strict_morpheme_errors=strict)


def test_unknown_morpheme_warns_and_falls_back() -> None:
    dictionary = _dictionary_without_return(strict=False)
    encoder = QYNEncoder(dictionary=dictionary)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UnknownMorphemeWarning)
        stream = encoder.encode("def foo(x):\n    return x + 1\n")
    assert any(isinstance(item.message, UnknownMorphemeWarning) for item in caught)
    unknown_entry = dictionary.entry_for_key("meta:unknown")
    assert unknown_entry is not None
    assert f"{unknown_entry.morpheme}<{unknown_entry.key}>" in stream.human_readable


def test_strict_morpheme_errors_abort_encoding() -> None:
    dictionary = _dictionary_without_return(strict=True)
    encoder = QYNEncoder(dictionary=dictionary, strict_morpheme_errors=True)
    with pytest.raises(UnknownMorphemeError):
        encoder.encode("def foo(x):\n    return x + 1\n")


def test_cli_strict_flag_surfaces_unknown_morphemes(tmp_path, monkeypatch) -> None:
    source = tmp_path / "module.py"
    source.write_text("def foo(x):\n    return x + 1\n", encoding="utf-8")
    key_file = tmp_path / "key.txt"
    key_file.write_text("secret\n", encoding="utf-8")
    dictionary = _dictionary_without_return(strict=True)
    monkeypatch.setattr(encoder_module, "load_dictionary", lambda version="1.0", **_: dictionary)
    monkeypatch.setattr(cli, "QYNEncoder", encoder_module.QYNEncoder)
    args = argparse.Namespace(
        source=str(source),
        output=None,
        key=str(key_file),
        passphrase=None,
        human_readable=None,
        quiet=True,
        language=None,
        compression_backend="preset",
        compression_mode="balanced",
        model_mode="adaptive",
        strict_morpheme_errors=True,
    )
    with pytest.raises(cli.CommandError):
        cli.encode_command(args)
