"""Utilities for managing Quenyan package and dictionary versions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")


@dataclass(frozen=True, order=True)
class Version:
    """Minimal semantic version representation."""

    major: int
    minor: int
    patch: int = 0

    def __str__(self) -> str:  # pragma: no cover - trivial repr
        return self.text

    @property
    def text(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def short_text(self) -> str:
        if self.patch:
            return self.text
        return f"{self.major}.{self.minor}"

    @classmethod
    def parse(cls, value: str) -> "Version":
        match = _SEMVER_RE.match(value.strip())
        if not match:
            raise ValueError(f"Invalid semantic version '{value}'")
        major = int(match.group(1))
        minor = int(match.group(2))
        patch_text = match.group(3)
        patch = int(patch_text) if patch_text is not None else 0
        return cls(major, minor, patch)


CURRENT_PACKAGE_VERSION = Version(1, 2, 0)
MINIMUM_SUPPORTED_PACKAGE_VERSION = Version(1, 0, 0)

SUPPORTED_PACKAGE_VERSIONS: Tuple[Version, ...] = (
    Version(1, 0, 0),
    Version(1, 1, 0),
    CURRENT_PACKAGE_VERSION,
)


def parse_any_version(value: str) -> Version:
    """Parse *value* allowing historical shorthand versions."""

    normalized = value.strip()
    if normalized.count(".") == 1:
        major, minor = normalized.split(".")
        return Version(int(major), int(minor), 0)
    return Version.parse(normalized)


def ensure_supported(version: Version) -> None:
    """Raise if *version* falls outside the supported window."""

    if version.major != CURRENT_PACKAGE_VERSION.major:
        raise ValueError(
            f"Unsupported package major version {version.major}; "
            f"expected {CURRENT_PACKAGE_VERSION.major}"
        )
    if version < MINIMUM_SUPPORTED_PACKAGE_VERSION:
        raise ValueError(
            f"Package version {version.short_text} is below the minimum supported "
            f"{MINIMUM_SUPPORTED_PACKAGE_VERSION.short_text}"
        )


def compatibility_matrix(versions: Iterable[Version]) -> Dict[str, Dict[str, bool]]:
    """Return a decoder×file compatibility lookup table."""

    supported = sorted(set(SUPPORTED_PACKAGE_VERSIONS) | set(versions))
    matrix: Dict[str, Dict[str, bool]] = {}
    for decoder in supported:
        decoder_entry: Dict[str, bool] = {}
        for payload in supported:
            decoder_entry[payload.text] = decoder.major == payload.major and (
                decoder >= payload >= MINIMUM_SUPPORTED_PACKAGE_VERSION
            )
        matrix[decoder.text] = decoder_entry
    return matrix


def advertised_versions() -> Tuple[str, ...]:
    """Return the string forms of all known package revisions."""

    return tuple(version.text for version in SUPPORTED_PACKAGE_VERSIONS)


def negotiate_version(preferred: Iterable[str] | None) -> Version:
    """Select the best mutually supported version from *preferred*.

    If *preferred* is empty or ``None`` the current package version is
    returned. The negotiation is restricted to versions that share the
    current major version and lie within the supported compatibility window.
    """

    if preferred is None:
        return CURRENT_PACKAGE_VERSION
    parsed = {parse_any_version(value) for value in preferred}
    if not parsed:
        return CURRENT_PACKAGE_VERSION
    for candidate in sorted(SUPPORTED_PACKAGE_VERSIONS, reverse=True):
        if candidate in parsed:
            return candidate
    raise ValueError(
        "no compatible package version found for negotiation"
    )

