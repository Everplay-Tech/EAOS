import base64
import json
import subprocess
from pathlib import Path

import pytest

from qyn1 import QYNEncoder, encode_package, read_package
from reference.python import mcs_reference as py_ref

CANONICAL_VERSIONS = json.loads((Path(__file__).parent / "canonical_versions.json").read_text())

LANGUAGE_FEATURE_MATRIX = {
    "python": {"framed": True, "payload_channels": True},
    "rust": {"framed": True, "payload_channels": True},
    "go": {"framed": True, "payload_channels": True},
    "js": {"framed": True, "payload_channels": True},
    # TODO: Promote the TypeScript binding to parity coverage once the CLI is wired up.
    "ts": {"framed": False, "payload_channels": False},
}


def _require_features(language: str, *features: str) -> None:
    missing = [
        feature
        for feature in features
        if not LANGUAGE_FEATURE_MATRIX.get(language, {}).get(feature, False)
    ]
    if missing:
        pytest.skip(
            f"TODO: enable {', '.join(missing)} for {language} binding before parity enforcement"
        )


@pytest.fixture(scope="module")
def sample_package(tmp_path_factory):
    encoder = QYNEncoder()
    stream = encoder.encode(
        """
def parallax(x: float, scale: float) -> float:
    return (x * scale) / 3.14159
""".strip()
    )
    package = encode_package(stream)
    passphrase = "reference-passphrase"
    package_bytes = package.to_bytes(passphrase)
    descriptor = py_ref.decode(package_bytes, passphrase)
    return descriptor, package_bytes, passphrase


def _decode_in(language: str, package_bytes: bytes, passphrase: str):
    _require_features(language, "framed", "payload_channels")
    if language == "python":
        return py_ref.decode(package_bytes, passphrase)
    if language == "rust":
        output = _run_rust(
            [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                "reference/rust/Cargo.toml",
                "--",
                "decode",
                "--passphrase",
                passphrase,
            ],
            input_text=base64.b64encode(package_bytes).decode("ascii"),
        )
        return json.loads(output.stdout)
    if language == "go":
        output = _run_go(
            [
                "go",
                "run",
                ".",
                "--command",
                "decode",
                "--passphrase",
                passphrase,
            ],
            input_text=base64.b64encode(package_bytes).decode("ascii"),
        )
        return json.loads(output.stdout)
    if language == "js":
        output = _run_js(
            [
                "node",
                "reference/js/mcs.js",
                "decode",
                "--passphrase",
                passphrase,
            ],
            input_text=base64.b64encode(package_bytes).decode("ascii"),
        )
        return json.loads(output.stdout)
    raise ValueError(f"unknown language {language}")


def _encode_in(language: str, descriptor: dict, passphrase: str) -> bytes:
    _require_features(language, "framed", "payload_channels")
    descriptor_json = json.dumps(descriptor)
    if language == "python":
        return py_ref.encode(descriptor, passphrase)
    if language == "rust":
        output = _run_rust(
            [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                "reference/rust/Cargo.toml",
                "--",
                "encode",
                "--passphrase",
                passphrase,
            ],
            input_text=descriptor_json,
        )
        return base64.b64decode(output.stdout.strip())
    if language == "go":
        output = _run_go(
            [
                "go",
                "run",
                ".",
                "--command",
                "encode",
                "--passphrase",
                passphrase,
            ],
            input_text=descriptor_json,
        )
        return base64.b64decode(output.stdout.strip())
    if language == "js":
        output = _run_js(
            [
                "node",
                "reference/js/mcs.js",
                "encode",
                "--passphrase",
                passphrase,
            ],
            input_text=descriptor_json,
        )
        return base64.b64decode(output.stdout.strip())
    raise ValueError(f"unknown language {language}")


def _run_rust(command, *, input_text: str):
    try:
        return subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        if "failed to get" in stderr or "failed to download" in stderr:
            pytest.skip("Rust toolchain dependencies unavailable in test environment")
        raise


def _run_go(command, *, input_text: str):
    try:
        return subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=True,
            cwd="reference/go",
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        if (
            "module golang.org/x/crypto" in stderr
            or "missing go.sum entry" in stderr
            or "no Go compiler" in stderr
        ):
            pytest.skip("Go toolchain or modules unavailable in test environment")
        raise


def _run_js(command, *, input_text: str):
    try:
        return subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        if "Cannot find module" in stderr or "node: not found" in stderr:
            pytest.skip("JavaScript toolchain unavailable in test environment")
        raise


def test_cross_language_decoding_matches_python(sample_package):
    descriptor, package_bytes, passphrase = sample_package
    for language in ("rust", "go", "js"):
        decoded = _decode_in(language, package_bytes, passphrase)
        assert decoded == descriptor


@pytest.mark.parametrize(
    ("encode_lang", "decode_lang"),
    [("rust", "go"), ("go", "js"), ("js", "rust")],
)
def test_cross_language_framing_and_streaming_parity(
    sample_package, encode_lang: str, decode_lang: str
):
    descriptor, _, passphrase = sample_package
    encoded = _encode_in(encode_lang, descriptor, passphrase)
    decoded = _decode_in(decode_lang, encoded, passphrase)
    assert decoded == descriptor

    stream = read_package(encoded, passphrase)
    assert stream.dictionary_version == CANONICAL_VERSIONS["dictionary_version"]
