"""Language detection helpers that combine extension, MIME, and content signals."""

from __future__ import annotations

import codecs
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple, Union

from .language_profiles import (
    LanguageProfile,
    default_registry,
    profile_for_extension,
    profile_for_mime,
    profile_for_path,
    resolve_profile_spec,
)

UserProfileSpec = Union[str, LanguageProfile, Path]


@dataclass(frozen=True)
class LanguageDetectionResult:
    """Outcome of the language detection pipeline."""

    language: str
    profile: LanguageProfile
    reason: str
    confidence: float
    encoding: Optional[str] = None


def _detect_bom_encoding(content: bytes) -> Optional[str]:
    if content.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if content.startswith(codecs.BOM_UTF16_LE):
        return "utf-16le"
    if content.startswith(codecs.BOM_UTF16_BE):
        return "utf-16be"
    if b"\x00" in content[:200]:
        # Heuristic for UTF-16 data that lacks an explicit BOM.
        if all(byte == 0 for byte in content[1:200:2]):
            return "utf-16le"
        if all(byte == 0 for byte in content[0:200:2]):
            return "utf-16be"
    return None


def _decode_preview(content: bytes) -> str:
    encoding = _detect_bom_encoding(content)
    if encoding:
        return content.decode(encoding, errors="ignore")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="ignore")


def _content_hints(content: bytes) -> Dict[str, Tuple[float, str]]:
    text = _decode_preview(content)
    hints: Dict[str, Tuple[float, str]] = {}
    lowered = text.lower()
    if "macro_rules!" in text or "#![macro_use]" in text:
        hints["rust"] = (0.9, "found rust macro syntax")
    if "template<" in text or "typename" in text or "std::" in text:
        hints["cpp"] = (0.7, "found c++ template markers")
    if "package main" in lowered or re.search(r"\bfunc\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(", text):
        hints["go"] = (0.85, "found go package or function declaration")
    if "fmt.Println" in text or "make(" in text:
        hints.setdefault("go", (0.65, "common go stdlib calls"))
    if "import " in lowered and ("from \"" in text or "from '" in text):
        hints["javascript"] = (0.6, "found esm import syntax")
    if "console.log" in lowered or "export default" in lowered:
        hints.setdefault("javascript", (0.55, "common javascript keywords"))
    if "jsx" in lowered or "react" in text or "return (" in text:
        hints["jsx"] = (0.75, "found JSX invocation")
    if "@" in text and ("decorator" in lowered or "Component" in text or "Injectable" in text):
        hints["typescript"] = (0.65, "decorator syntax detected")
    elif re.search(r"@[A-Za-z_][A-Za-z0-9_]*\s*(?:\(|$)", text):
        hints["typescript"] = (0.65, "decorator syntax detected")
    if "interface " in lowered and ":" in text:
        hints.setdefault("typescript", (0.55, "interface declaration"))
    return hints


def detect_language(
    path: Path,
    content: Optional[bytes] = None,
    *,
    language_hint: Optional[Union[str, Path]] = None,
    user_profiles: Optional[Mapping[str, UserProfileSpec]] = None,
    default: str = "python",
) -> LanguageDetectionResult:
    """Detect the best language profile for *path*.

    The detector combines file extension heuristics, MIME-style guesses, simple
    content pattern matching and optional user supplied overrides. The returned
    :class:`LanguageDetectionResult` reports the winning profile along with a
    confidence score and reasoning string.
    """

    scores: Dict[str, Tuple[float, list[str], LanguageProfile]] = {}
    registry = default_registry()

    def register(profile: LanguageProfile, boost: float, reason: str) -> None:
        current = scores.get(profile.name)
        if current is None:
            scores[profile.name] = (min(boost, 1.0), [reason], profile)
            return
        score, reasons, existing = current
        score = min(score + boost, 1.0)
        reasons.append(reason)
        scores[profile.name] = (score, reasons, existing)

    if language_hint:
        profile = resolve_profile_spec(language_hint, registry=registry)
        register(profile, 1.0, f"explicit language hint {profile.name}")

    ext = path.suffix.lower()
    extension_profile = profile_for_extension(ext, registry=registry)
    if extension_profile:
        register(extension_profile, 0.6, f"extension match {ext}")

    guessed_mime = mimetypes.guess_type(path.name)[0]
    if guessed_mime:
        mime_profile = profile_for_mime(guessed_mime.lower(), registry=registry)
        if mime_profile:
            register(mime_profile, 0.4, f"mimetype guess {guessed_mime}")

    detected_encoding: Optional[str] = None
    if content is not None:
        detected_encoding = _detect_bom_encoding(content)
        hints = _content_hints(content)
        for language, (boost, reason) in hints.items():
            try:
                profile = resolve_profile_spec(language, registry=registry)
            except Exception:
                continue
            register(profile, boost, reason)

    if user_profiles:
        key = ext.lstrip(".")
        spec = user_profiles.get(ext) or user_profiles.get(key)
        if spec is not None:
            profile = resolve_profile_spec(spec, registry=registry)
            register(profile, 0.95, f"user override for {ext or key}")

    if not scores:
        fallback_profile = profile_for_path(
            path,
            registry=registry,
            language_hint=language_hint,
            mime_type=guessed_mime.lower() if guessed_mime else None,
            fallback=default,
        )
        register(fallback_profile, 0.1, f"fallback to default profile {fallback_profile.name}")

    best_score = -1.0
    best_profile: Optional[LanguageProfile] = None
    best_reason = ""
    for score, reasons, profile in scores.values():
        if score > best_score:
            best_score = score
            best_profile = profile
            best_reason = "; ".join(reasons)
    assert best_profile is not None

    if detected_encoding is None and content is not None:
        detected_encoding = best_profile.preferred_encodings[0] if best_profile.preferred_encodings else None

    return LanguageDetectionResult(
        language=best_profile.name,
        profile=best_profile,
        reason=best_reason,
        confidence=min(max(best_score, 0.0), 1.0),
        encoding=detected_encoding,
    )
