import json
from pathlib import Path

import pytest

from qyn1.language_detection import detect_language

FIXTURE_DIR = Path("tests/language_roundtrip")
UTF16_SPEC = FIXTURE_DIR / "wide_cpp_utf16.json"


def _fixture(name: str) -> Path:
    path = FIXTURE_DIR / name
    if not path.exists():
        pytest.skip(f"fixture {name} is not available")
    return path


def _utf16_fixture(tmp_path: Path) -> Path:
    if not UTF16_SPEC.exists():
        pytest.skip("utf-16 fixture is not available")

    with UTF16_SPEC.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    encoding = payload.get("encoding", "utf-16")
    filename = payload.get("filename", "wide.cpp")
    source = payload["source"]

    path = tmp_path / filename
    path.write_bytes(source.encode(encoding))
    return path


def test_detects_typescript_decorators() -> None:
    path = _fixture("decorator.ts")
    result = detect_language(path, path.read_bytes())
    assert result.language == "typescript"
    assert "decorator" in result.reason


def test_detects_jsx_payload() -> None:
    path = _fixture("component.tsx")
    result = detect_language(path, path.read_bytes())
    assert result.language == "jsx"
    assert "JSX" in result.reason or "jsx" in result.reason.lower()


def test_detects_rust_macro() -> None:
    path = _fixture("macro.rs")
    result = detect_language(path, path.read_bytes())
    assert result.language == "rust"
    assert "macro" in result.reason


def test_detect_utf16_cpp_source(tmp_path: Path) -> None:
    path = _utf16_fixture(tmp_path)
    result = detect_language(path, path.read_bytes())
    assert result.language == "cpp"
    text, encoding = result.profile.decode_source(path.read_bytes())
    assert encoding.lower().startswith("utf-16")
    assert not text.startswith("\ufeff")
