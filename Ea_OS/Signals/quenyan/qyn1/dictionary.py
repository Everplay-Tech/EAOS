"""Versioned Quenya morpheme dictionary management."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from importlib import resources
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .versioning import CURRENT_PACKAGE_VERSION, Version, parse_any_version

_DEFAULT_VERSION = "1.0"
_RESOURCE_PACKAGE = "qyn1.resources.morpheme_dictionary"
_DICTIONARY_FILES: Mapping[str, str] = {
    "1.0": "v1_0/dictionary.json",
}

# Map exposed dictionary revisions to the on-disk resource set they reuse.
COMPATIBILITY_TABLE: Mapping[str, str] = {
    "1.0": "1.0",
    "1.0.0": "1.0",
    "1.1": "1.0",
    "1.1.0": "1.0",
    "1.2": "1.0",
    "1.2.0": "1.0",
}

# (min_version, max_version)
_DICTIONARY_COMPATIBILITY: Mapping[str, Tuple[Version, Version]] = {
    "1.0": (parse_any_version("1.0"), CURRENT_PACKAGE_VERSION),
}


class UnknownMorphemeWarning(UserWarning):
    """Raised when an unknown key is resolved to the fallback morpheme."""


class UnknownMorphemeError(LookupError):
    """Raised when strict morpheme resolution is enabled and a key is missing."""


@dataclass(frozen=True)
class MorphemeEntry:
    """Immutable description of a single morpheme mapping."""

    key: str
    morpheme: str
    quenya_root: str
    gloss: str
    linguistic_justification: str
    ast_nodes: List[str]
    frequency_per_10k_loc: int
    encoding: Dict[str, Any]


class MorphemeDictionary:
    """Lookup structure over the canonical morpheme dictionary."""

    def __init__(
        self,
        version: str,
        entries: Iterable[MorphemeEntry],
        *,
        strict_morpheme_errors: bool = False,
    ):
        self.version = version
        self.strict_morpheme_errors = strict_morpheme_errors
        self._entries: List[MorphemeEntry] = list(entries)
        self._key_to_index: Dict[str, int] = {}
        self._morpheme_to_index: Dict[str, int] = {}
        for index, entry in enumerate(self._entries):
            self._key_to_index.setdefault(entry.key, index)
            self._morpheme_to_index.setdefault(entry.morpheme, index)
        try:
            self._unknown_index = self._key_to_index["meta:unknown"]
        except KeyError as exc:  # pragma: no cover - sanity guard
            raise ValueError("Dictionary must contain meta:unknown entry") from exc

    # ------------------------------------------------------------------
    # Accessors

    def __len__(self) -> int:  # pragma: no cover - trivial proxy
        return len(self._entries)

    @property
    def entries(self) -> List[MorphemeEntry]:
        return list(self._entries)

    def entry_for_index(self, index: int) -> MorphemeEntry:
        return self._entries[index]

    def index_for_key(self, key: str, *, strict: bool | None = None) -> int:
        strict_mode = self.strict_morpheme_errors if strict is None else strict
        if key in self._key_to_index:
            return self._key_to_index[key]
        if strict_mode:
            raise UnknownMorphemeError(f"Unknown morpheme key {key!r}")
        warnings.warn(
            f"Unknown morpheme key {key!r}; using fallback",
            UnknownMorphemeWarning,
            stacklevel=2,
        )
        return self._unknown_index

    def key_for_index(self, index: int) -> str:
        return self._entries[index].key

    def morpheme_for_key(self, key: str) -> str:
        return self._entries[self.index_for_key(key)].morpheme

    def entry_for_key(self, key: str) -> Optional[MorphemeEntry]:
        index = self._key_to_index.get(key)
        return None if index is None else self._entries[index]

    def serialize(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "entries": [entry.__dict__ for entry in self._entries],
        }

    # ------------------------------------------------------------------
    # Human readable helpers

    def humanize(self, indices: Iterable[int]) -> List[str]:
        human: List[str] = []
        for index in indices:
            entry = self.entry_for_index(index)
            human.append(f"{entry.morpheme}<{entry.key}>")
        return human


def _resolve_version(version: str) -> str:
    parsed = parse_any_version(version)
    key = parsed.text if parsed.patch else parsed.short_text
    try:
        return COMPATIBILITY_TABLE[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported dictionary version: {version}") from exc


def _path_for_version(version: str) -> str:
    resolved = _resolve_version(version)
    try:
        return _DICTIONARY_FILES[resolved]
    except KeyError as exc:  # pragma: no cover - sanity guard
        raise ValueError(f"Unsupported dictionary version: {version}") from exc


def _load_json(version: str) -> Dict[str, Any]:
    relative_path = _path_for_version(version)
    package = resources.files(_RESOURCE_PACKAGE)
    data_text = package.joinpath(*relative_path.split("/")).read_text("utf-8")
    return json.loads(data_text)


def ensure_dictionary_supported(version: str, *, package_version: Version | None = None) -> None:
    """Validate that *version* can be emitted by the running encoder."""

    package_version = package_version or CURRENT_PACKAGE_VERSION
    resolved = _resolve_version(version)
    try:
        minimum, maximum = _DICTIONARY_COMPATIBILITY[resolved]
    except KeyError as exc:  # pragma: no cover - sanity guard
        raise ValueError(f"Unsupported dictionary version: {version}") from exc
    if not (minimum <= package_version <= maximum):
        raise ValueError(
            "Dictionary version "
            f"{version} incompatible with package {package_version.text}"
        )


def compatibility_map() -> Mapping[str, Tuple[str, str]]:
    """Return the declared compatibility window for each dictionary."""

    return {
        version: (minimum.text, maximum.text)
        for version, (minimum, maximum) in _DICTIONARY_COMPATIBILITY.items()
    }


def load_dictionary(
    version: str = _DEFAULT_VERSION, *, strict_morpheme_errors: bool = False
) -> MorphemeDictionary:
    """Load the morpheme dictionary for *version*."""

    ensure_dictionary_supported(version)
    resolved = _resolve_version(version)
    raw = _load_json(resolved)
    expected_version = parse_any_version(version).short_text
    payload_version = str(raw.get("version", resolved))
    if payload_version not in {expected_version, resolved}:
        raise ValueError(
            "Dictionary payload version mismatch: "
            f"expected {expected_version} or {resolved}, got {payload_version}"
        )
    entries = [
        MorphemeEntry(
            key=item["key"],
            morpheme=item["morpheme"],
            quenya_root=item["quenya_root"],
            gloss=item["gloss"],
            linguistic_justification=item["linguistic_justification"],
            ast_nodes=list(item.get("ast_nodes", [])),
            frequency_per_10k_loc=int(item["frequency_per_10k_loc"]),
            encoding=dict(item.get("encoding", {})),
        )
        for item in raw["entries"]
    ]
    return MorphemeDictionary(
        version=expected_version,
        entries=entries,
        strict_morpheme_errors=strict_morpheme_errors,
    )
