"""Utilities for encoding files with language-aware decoding."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Union

from .encoder import EncodedStream, QYNEncoder
from .encoder import HumanBuffer, TokenBuffer  # type: ignore
from .language_detection import LanguageDetectionResult, detect_language
from .language_profiles import LanguageProfile

UserProfileSpec = Union[str, LanguageProfile]


def encode_file_with_options(
    path: Path,
    encoder: QYNEncoder,
    *,
    language_hint: Optional[str] = None,
    profile_overrides: Optional[Mapping[str, UserProfileSpec]] = None,
    token_buffer: Optional[TokenBuffer] = None,
    human_buffer: Optional[HumanBuffer] = None,
) -> tuple[EncodedStream, LanguageDetectionResult]:
    """Encode *path* using *encoder* with language-aware decoding.

    The file is read as bytes, passed through :func:`detect_language` to obtain a
    suitable :class:`LanguageProfile` and decoded using the profile's preferred
    encodings. The resulting :class:`EncodedStream` is returned alongside the
    detection result so callers can inspect confidence and reasoning.
    """

    raw = path.read_bytes()
    detection = detect_language(
        path,
        raw,
        language_hint=language_hint,
        user_profiles=profile_overrides,
        default=encoder.language_profile_name,
    )
    profile = detection.profile
    text, encoding = profile.decode_source(raw)
    stream = encoder.encode(
        text,
        token_buffer=token_buffer,
        human_buffer=human_buffer,
        language_profile=profile,
        source_encoding=encoding,
    )
    return stream, detection
