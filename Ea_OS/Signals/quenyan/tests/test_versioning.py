from pathlib import Path

import pytest

from qyn1.package import decode_package
from qyn1.versioning import (
    CURRENT_PACKAGE_VERSION,
    MINIMUM_SUPPORTED_PACKAGE_VERSION,
    advertised_versions,
    compatibility_matrix,
    ensure_supported,
    parse_any_version,
)


ARCHIVE_ROOT = Path(__file__).parent / "data" / "compatibility"


def _archive_files():
    return sorted(ARCHIVE_ROOT.rglob("*.mcs"))


def test_archive_contains_at_least_one_hundred_cases() -> None:
    files = _archive_files()
    assert len(files) >= 100


@pytest.mark.parametrize("path", _archive_files())
def test_decoder_can_read_archived_packages(path: Path) -> None:
    payload = path.read_bytes()
    stream = decode_package(payload, "compatibility")
    assert stream.dictionary_version >= MINIMUM_SUPPORTED_PACKAGE_VERSION.short_text
    assert stream.tokens


def test_version_parsing_and_support_window() -> None:
    for text in ("1.0", "1.1.0", CURRENT_PACKAGE_VERSION.text):
        version = parse_any_version(text)
        ensure_supported(version)
    with pytest.raises(ValueError):
        ensure_supported(parse_any_version("0.9"))


def test_advertised_versions_are_consistent() -> None:
    versions = advertised_versions()
    matrix = compatibility_matrix(parse_any_version(item) for item in versions)
    current = CURRENT_PACKAGE_VERSION.text
    assert matrix[current][current]
    for decoder, entries in matrix.items():
        for payload, supported in entries.items():
            if payload < MINIMUM_SUPPORTED_PACKAGE_VERSION.text:
                assert not supported
