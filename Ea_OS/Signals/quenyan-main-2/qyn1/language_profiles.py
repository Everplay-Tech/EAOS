"""Language profile discovery, resolution, and registration utilities.

The language profile registry is intentionally extensible. External plugins can
register custom profiles by:

* Shipping JSON manifests that match the schema used by the bundled files in
  :mod:`qyn1.data.language_profiles`. These can be loaded at runtime via
  :func:`register_manifest_path` or passed directly to CLI commands that accept
  a ``--language`` manifest path.
* Providing Python modules that expose either a ``register_language_profiles``
  hook or a ``language_profiles``/``LANGUAGE_PROFILES`` iterable of
  :class:`LanguageProfile` objects. Use :func:`register_language_module` to load
  these at startup.

When combined with :func:`profile_for_path`, callers can resolve profiles using
file names, MIME types, or explicit selectors without needing to modify the core
encoder.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union


@dataclass(frozen=True)
class LiteralProfile:
    """Description of literal encoding keys used by a language profile."""

    bool_true: str
    bool_false: str
    null: str
    string: str
    bytes: str
    integer: str
    floating: str
    template: str
    fallback: str
    wide_string: Optional[str] = None


@dataclass(frozen=True)
class LanguageProfile:
    """Data-driven configuration describing how to interpret AST nodes."""

    name: str
    version: str
    aliases: Tuple[str, ...]
    extensions: Tuple[str, ...]
    mime_types: Tuple[str, ...]
    type_aliases: Mapping[str, str]
    reverse_type_aliases: Mapping[str, str]
    binary_operators: Mapping[str, str]
    unary_operators: Mapping[str, str]
    literal_profile: LiteralProfile
    preferred_encodings: Tuple[str, ...]
    template_payloads: Mapping[str, str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def normalise_type_name(self, name: str) -> Optional[str]:
        """Return the canonical morpheme key for *name* if available."""

        return self.type_aliases.get(name.lower())

    def render_type_name(self, key: str) -> Optional[str]:
        """Return a human readable name for the canonical type key."""

        return self.reverse_type_aliases.get(key)

    def binary_operator_key(self, operator_name: str) -> str:
        """Return the morpheme key for the binary operator with *operator_name*."""

        return self.binary_operators.get(operator_name, self.literal_profile.fallback)

    def unary_operator_key(self, operator_name: str) -> str:
        """Return the morpheme key for the unary operator with *operator_name*."""

        return self.unary_operators.get(operator_name, self.literal_profile.fallback)

    def decode_source(self, data: bytes) -> Tuple[str, str]:
        """Decode *data* using the profile's preferred encodings.

        Returns a tuple of ``(text, encoding)`` where *text* is a ``str`` that is
        suitable for parsing and *encoding* records the codec that succeeded. If
        no encoding in :attr:`preferred_encodings` is suitable, the first
        successful UTF-8 decode is returned as a last resort.
        """

        last_error: Optional[UnicodeDecodeError] = None
        for encoding in self.preferred_encodings:
            try:
                text = data.decode(encoding)
                return text.lstrip("\ufeff"), encoding
            except UnicodeDecodeError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        text = data.decode("utf-8")
        return text.lstrip("\ufeff"), "utf-8"


def _parse_literal_profile(raw: Mapping[str, Any]) -> LiteralProfile:
    literals = raw.get("literals", {})
    required = [
        "bool_true",
        "bool_false",
        "null",
        "string",
        "bytes",
        "integer",
        "float",
        "template",
        "fallback",
    ]
    missing = [name for name in required if name not in literals]
    if missing:
        raise ValueError(f"Profile literals missing required keys: {missing}")
    return LiteralProfile(
        bool_true=literals["bool_true"],
        bool_false=literals["bool_false"],
        null=literals["null"],
        string=literals["string"],
        bytes=literals["bytes"],
        integer=literals["integer"],
        floating=literals["float"],
        template=literals["template"],
        fallback=literals["fallback"],
        wide_string=literals.get("wide_string"),
    )


def _parse_profile(raw: Mapping[str, Any]) -> LanguageProfile:
    literal_profile = _parse_literal_profile(raw)
    extensions = tuple(ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in raw.get("extensions", []))
    mime_types = tuple(mt.lower() for mt in raw.get("mime_types", []))
    return LanguageProfile(
        name=raw["language"],
        version=raw.get("version", "1.0"),
        aliases=tuple(alias.lower() for alias in raw.get("aliases", [])),
        extensions=extensions,
        mime_types=mime_types,
        type_aliases={key.lower(): value for key, value in raw.get("type_aliases", {}).items()},
        reverse_type_aliases={key: value for key, value in raw.get("reverse_type_aliases", {}).items()},
        binary_operators=dict(raw.get("binary_operators", {})),
        unary_operators=dict(raw.get("unary_operators", {})),
        literal_profile=literal_profile,
        preferred_encodings=tuple(raw.get("preferred_encodings", ["utf-8"])),
        template_payloads=dict(raw.get("template_payloads", {})),
        metadata=dict(raw.get("metadata", {})),
    )


def _profiles_package() -> resources.abc.Traversable:
    return resources.files("qyn1.data").joinpath("language_profiles")


class LanguageProfileRegistry:
    """Registry for built-in and user-provided language profiles."""

    def __init__(self) -> None:
        self._profiles: Dict[str, LanguageProfile] = {}
        self._aliases: Dict[str, str] = {}
        self._extension_index: Dict[str, List[str]] = {}
        self._mime_index: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------ #
    # Registration

    def register_profile(self, profile: LanguageProfile, *, override: bool = False) -> None:
        """Register *profile* and update alias and extension indexes."""

        canonical = profile.name.lower()
        if canonical in self._profiles and not override:
            return
        self._profiles[canonical] = profile
        self._aliases.setdefault(canonical, profile.name)
        for alias in profile.aliases:
            if override or alias not in self._aliases:
                self._aliases[alias] = profile.name
        for ext in profile.extensions:
            ext_lower = ext.lower()
            current = self._extension_index.setdefault(ext_lower, [])
            if profile.name not in current:
                current.append(profile.name)
        for mime in profile.mime_types:
            mime_lower = mime.lower()
            current = self._mime_index.setdefault(mime_lower, [])
            if profile.name not in current:
                current.append(profile.name)

    def register_manifest_path(self, path: Union[str, Path], *, override: bool = False) -> LanguageProfile:
        """Load a manifest from *path* and register it."""

        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        profile = _parse_profile(raw)
        self.register_profile(profile, override=override)
        return profile

    def register_manifest_loader(self, loader: Callable[[], Mapping[str, Any]], *, override: bool = False) -> LanguageProfile:
        """Load a manifest via *loader* and register the resulting profile."""

        profile = _parse_profile(loader())
        self.register_profile(profile, override=override)
        return profile

    def register_module(self, module: Union[str, ModuleType]) -> None:
        """Register profiles exposed by *module*.

        Modules can provide a ``register_language_profiles(registry)`` hook or a
        ``language_profiles``/``LANGUAGE_PROFILES`` iterable of ready-made
        :class:`LanguageProfile` instances.
        """

        if isinstance(module, str):
            module = importlib.import_module(module)
        hook = getattr(module, "register_language_profiles", None)
        if callable(hook):
            hook(self)
            return
        candidates = getattr(module, "language_profiles", None) or getattr(module, "LANGUAGE_PROFILES", None)
        if candidates:
            for profile in candidates:
                self.register_profile(profile, override=True)

    # ------------------------------------------------------------------ #
    # Queries

    def available_profiles(self) -> List[str]:
        """Return the list of canonical profile names known to the registry."""

        names = sorted(self._profiles.keys())
        return names

    def resolve(self, name: Optional[str], *, fallback: str = "python") -> LanguageProfile:
        """Resolve *name* or *fallback* to a registered profile."""

        target = fallback if name is None else name
        canonical = self._aliases.get(target.lower())
        if canonical is None:
            raise ValueError(f"Unknown language profile: {target}")
        return self._profiles[canonical.lower()]

    def profile_from_alias(self, alias: str) -> Optional[LanguageProfile]:
        """Return the profile bound to *alias* if present."""

        canonical = self._aliases.get(alias.lower())
        if canonical is None:
            return None
        return self._profiles[canonical.lower()]

    def profiles_for_extension(self, extension: str) -> Tuple[LanguageProfile, ...]:
        """Return profiles that claim *extension* (leading dot optional)."""

        ext = extension if extension.startswith(".") else f".{extension}"
        return tuple(self._profiles[name.lower()] for name in self._extension_index.get(ext.lower(), ()))

    def profiles_for_mime(self, mime: str) -> Tuple[LanguageProfile, ...]:
        """Return profiles that declare *mime*."""

        return tuple(self._profiles[name.lower()] for name in self._mime_index.get(mime.lower(), ()))

    def extension_index(self) -> Dict[str, Tuple[LanguageProfile, ...]]:
        return {ext: tuple(self._profiles[name.lower()] for name in names) for ext, names in self._extension_index.items()}

    def mime_index(self) -> Dict[str, Tuple[LanguageProfile, ...]]:
        return {mime: tuple(self._profiles[name.lower()] for name in names) for mime, names in self._mime_index.items()}

    # ------------------------------------------------------------------ #
    # Built-in helpers

    @classmethod
    def with_builtin_profiles(cls) -> "LanguageProfileRegistry":
        """Create a registry populated with built-in manifest data."""

        registry = cls()
        package = _profiles_package()
        for entry in package.iterdir():
            if entry.name.endswith(".json"):
                raw = json.loads(entry.read_text("utf-8"))
                profile = _parse_profile(raw)
                registry.register_profile(profile)
        return registry


@lru_cache(maxsize=None)
def default_registry() -> LanguageProfileRegistry:
    return LanguageProfileRegistry.with_builtin_profiles()


def load_language_profile(name: str) -> LanguageProfile:
    """Load the language profile identified by *name* or alias."""

    return default_registry().resolve(name)


def load_profile_from_path(path: Union[str, Path]) -> LanguageProfile:
    """Load a language profile manifest from an explicit filesystem path."""

    return default_registry().register_manifest_path(path, override=True)


def available_profiles() -> List[str]:
    """Return the list of canonical profile names shipped with the package."""

    return default_registry().available_profiles()


def resolve_profile(name: Optional[str], fallback: str = "python") -> LanguageProfile:
    """Resolve *name* to a profile, using *fallback* when None."""

    return default_registry().resolve(name, fallback=fallback)


def resolve_profile_spec(
    spec: Optional[Union[str, Path, LanguageProfile]],
    *,
    registry: Optional[LanguageProfileRegistry] = None,
    fallback: str = "python",
    allow_manifest_paths: bool = True,
) -> LanguageProfile:
    """Resolve *spec* to a :class:`LanguageProfile`.

    ``spec`` may be a profile instance, a canonical name, an alias, or a path to
    a manifest JSON file. When ``spec`` is ``None`` the *fallback* profile is
    returned. This helper is intended to centralise the selection logic used by
    CLI flags and programmatic APIs.
    """

    registry = registry or default_registry()
    if isinstance(spec, LanguageProfile):
        return spec
    if spec is None:
        return registry.resolve(fallback)
    if isinstance(spec, Path):
        if allow_manifest_paths and spec.exists():
            return registry.register_manifest_path(spec, override=True)
        spec = str(spec)
    try:
        return registry.resolve(spec)
    except ValueError:
        if allow_manifest_paths:
            path = Path(spec)
            if path.exists():
                return registry.register_manifest_path(path, override=True)
        raise


def profile_for_extension(
    extension: str, *, registry: Optional[LanguageProfileRegistry] = None
) -> Optional[LanguageProfile]:
    """Return a profile declared for *extension* (leading dot optional)."""

    registry = registry or default_registry()
    profiles = registry.profiles_for_extension(extension)
    return profiles[0] if profiles else None


def profile_for_mime(mime: str, *, registry: Optional[LanguageProfileRegistry] = None) -> Optional[LanguageProfile]:
    """Return a profile registered for *mime* if available."""

    registry = registry or default_registry()
    profiles = registry.profiles_for_mime(mime)
    return profiles[0] if profiles else None


def profile_for_path(
    path: Union[str, Path],
    *,
    registry: Optional[LanguageProfileRegistry] = None,
    language_hint: Optional[Union[str, LanguageProfile]] = None,
    mime_type: Optional[str] = None,
    fallback: str = "python",
) -> LanguageProfile:
    """Resolve the best profile for *path* using extension, MIME, or hints.

    The function prioritises explicit ``language_hint`` (including manifest
    paths), then MIME matches, then file extensions. If none of these yield a
    match the ``fallback`` profile is returned.
    """

    registry = registry or default_registry()
    if language_hint is not None:
        return resolve_profile_spec(language_hint, registry=registry, fallback=fallback)

    if mime_type:
        profile = profile_for_mime(mime_type, registry=registry)
        if profile is not None:
            return profile

    profile = profile_for_extension(Path(path).suffix, registry=registry)
    if profile is not None:
        return profile

    return registry.resolve(fallback)


def register_language_module(module: Union[str, ModuleType]) -> None:
    """Register profiles from *module* in the shared registry."""

    default_registry().register_module(module)


__all__ = [
    "LiteralProfile",
    "LanguageProfile",
    "LanguageProfileRegistry",
    "available_profiles",
    "default_registry",
    "load_language_profile",
    "load_profile_from_path",
    "register_language_module",
    "resolve_profile",
    "resolve_profile_spec",
    "profile_for_extension",
    "profile_for_mime",
    "profile_for_path",
]
