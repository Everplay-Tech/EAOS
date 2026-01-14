from __future__ import annotations

from __future__ import annotations

from pathlib import Path

import pytest

import qyn1.package as package_module
from qyn1 import encode_package
from qyn1.format import read_frame
from qyn1.package import read_package, write_package
from qyn1.versioning import MINIMUM_SUPPORTED_PACKAGE_VERSION

ARCHIVE_ROOT = Path(__file__).resolve().parents[1] / "data" / "compatibility"


def _archive_files() -> list[Path]:
    return sorted(ARCHIVE_ROOT.rglob("*.mcs"))


@pytest.mark.parametrize("path", _archive_files())
def test_historical_packages_round_trip(path: Path) -> None:
    payload = path.read_bytes()
    original = read_package(payload, "compatibility")
    package = encode_package(original)
    rebuilt = write_package(package, "compatibility")
    frame, remainder = read_frame(rebuilt, expected_magic=package_module.WRAPPER_MAGIC)
    assert not remainder
    assert frame.version >= MINIMUM_SUPPORTED_PACKAGE_VERSION
    regenerated = read_package(rebuilt, "compatibility")
    assert regenerated.tokens == original.tokens
    assert regenerated.payloads == original.payloads
    if original.source_map is not None:
        assert regenerated.source_map is not None
        assert regenerated.source_map.entries == original.source_map.entries


def test_crc_detection() -> None:
    path = _archive_files()[0]
    payload = path.read_bytes()
    original = read_package(payload, "compatibility")
    package = encode_package(original)
    rebuilt = bytearray(write_package(package, "compatibility"))
    rebuilt[-1] ^= 0xFF
    with pytest.raises(ValueError):
        read_package(bytes(rebuilt), "compatibility")
