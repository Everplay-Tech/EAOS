import base64
import json
import subprocess

import pytest

from qyn1 import QYNEncoder, encode_package
from reference.python import mcs_reference as py_ref


@pytest.fixture()
def sample_descriptor(tmp_path):
    encoder = QYNEncoder()
    stream = encoder.encode(
        """
from math import sqrt


def hypotenuse(a: float, b: float) -> float:
    total = a * a + b * b
    return sqrt(total)
""".strip()
    )
    package = encode_package(stream)
    passphrase = "reference-passphrase"
    package_bytes = package.to_bytes(passphrase)
    descriptor = py_ref.decode(package_bytes, passphrase)
    return descriptor, package_bytes, passphrase


def test_python_reference_roundtrip(sample_descriptor):
    descriptor, package_bytes, passphrase = sample_descriptor
    rebuilt = py_ref.encode(descriptor, passphrase)
    assert rebuilt == package_bytes


def test_rust_reference_roundtrip(sample_descriptor):
    descriptor, package_bytes, passphrase = sample_descriptor
    descriptor_json = json.dumps(descriptor)
    rust_decode = _run_with_skip(
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
    rust_descriptor = json.loads(rust_decode.stdout)
    assert rust_descriptor == descriptor

    rust_encode = _run_with_skip(
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
    encoded_bytes = base64.b64decode(rust_encode.stdout.strip())
    assert encoded_bytes == package_bytes


def test_js_reference_roundtrip(sample_descriptor):
    descriptor, package_bytes, passphrase = sample_descriptor
    descriptor_json = json.dumps(descriptor)
    js_decode = _run_js_with_skip(
        [
            "node",
            "reference/js/mcs.js",
            "decode",
            "--passphrase",
            passphrase,
        ],
        input_text=base64.b64encode(package_bytes).decode("ascii"),
    )
    js_descriptor = json.loads(js_decode.stdout)
    assert js_descriptor == descriptor

    js_encode = _run_js_with_skip(
        [
            "node",
            "reference/js/mcs.js",
            "encode",
            "--passphrase",
            passphrase,
        ],
        input_text=descriptor_json,
    )
    encoded_bytes = base64.b64decode(js_encode.stdout.strip())
    assert encoded_bytes == package_bytes


def test_go_reference_roundtrip(sample_descriptor):
    descriptor, package_bytes, passphrase = sample_descriptor
    descriptor_json = json.dumps(descriptor)
    go_decode = _run_go_with_skip(
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
    go_descriptor = json.loads(go_decode.stdout)
    assert go_descriptor == descriptor

    go_encode = _run_go_with_skip(
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
    encoded_bytes = base64.b64decode(go_encode.stdout.strip())
    assert encoded_bytes == package_bytes


def _run_with_skip(command, input_text: str):
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


def _run_go_with_skip(command, input_text: str):
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


def _run_js_with_skip(command, *, input_text: str):
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
