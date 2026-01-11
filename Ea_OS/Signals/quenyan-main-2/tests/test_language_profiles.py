from pathlib import Path

from qyn1.encoding_io import encode_file_with_options
from qyn1.encoder import QYNEncoder
from qyn1.language_detection import detect_language
from qyn1.language_profiles import default_registry, resolve_profile


def test_builtin_profiles_discoverable() -> None:
    registry = default_registry()
    for name in ("python", "rust", "go", "javascript", "typescript"):
        assert name in registry.available_profiles()


def test_alias_resolution_prefers_canonical() -> None:
    registry = default_registry()
    rust = registry.resolve("rs")
    assert rust.name == "rust"
    assert registry.profile_from_alias("rustlang") is rust


def test_extension_detection_for_go_and_js() -> None:
    go_path = Path("tests/language_roundtrip/hello.go")
    js_path = Path("tests/language_roundtrip/app.js")

    go_detection = detect_language(go_path, go_path.read_bytes())
    js_detection = detect_language(js_path, js_path.read_bytes())

    assert go_detection.language == "go"
    assert js_detection.language == "javascript"
    assert "extension match" in go_detection.reason
    assert "extension match" in js_detection.reason


def test_encoder_respects_explicit_and_inferred_profiles(tmp_path: Path) -> None:
    encoder = QYNEncoder()
    rust_profile = resolve_profile("rust")
    stream = encoder.encode("1 + 2", language_profile=rust_profile)
    assert stream.source_language == "rust"
    assert encoder.language_profile_name == "python"

    faux_go = tmp_path / "script.go"
    faux_go.write_text("value = 3 + 4\n", encoding="utf-8")
    stream, detection = encode_file_with_options(
        faux_go, encoder, language_hint=None, token_buffer=[], human_buffer=[]
    )
    assert detection.language == "go"
    assert stream.source_language == "go"


def test_profile_for_path_prefers_hint_and_extension(tmp_path: Path) -> None:
    from qyn1.language_profiles import profile_for_path

    hinted = profile_for_path(tmp_path / "example.js", language_hint="rust")
    assert hinted.name == "rust"

    js_profile = profile_for_path(tmp_path / "example.js")
    assert js_profile.name == "javascript"


def test_resolve_profile_spec_accepts_manifest_path(tmp_path: Path) -> None:
    manifest = tmp_path / "custom.json"
    manifest.write_text(
        """
        {
          "language": "examplelang",
          "version": "0.1",
          "aliases": ["example"],
          "extensions": [".ex"],
          "mime_types": ["text/example"],
          "preferred_encodings": ["utf-8"],
          "type_aliases": {"string": "type:string"},
          "reverse_type_aliases": {"type:string": "string"},
          "binary_operators": {},
          "unary_operators": {},
          "literals": {
            "bool_true": "literal:bool_true",
            "bool_false": "literal:bool_false",
            "null": "literal:null",
            "string": "literal:string",
            "bytes": "literal:array",
            "integer": "literal:int",
            "float": "literal:float",
            "template": "literal:template",
            "fallback": "meta:unknown"
          },
          "template_payloads": {}
        }
        """,
        encoding="utf-8",
    )

    from qyn1.language_profiles import resolve_profile_spec

    profile = resolve_profile_spec(manifest)
    assert profile.name == "examplelang"
    assert profile.extensions == (".ex",)


def test_encoder_infers_profile_from_path(tmp_path: Path) -> None:
    encoder = QYNEncoder()
    stream = encoder.encode("1 + 2", source_path=tmp_path / "calc.rs")
    assert stream.source_language == "rust"
    assert encoder.language_profile_name == "python"
