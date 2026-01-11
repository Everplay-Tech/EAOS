"""Model construction utilities for morpheme compression.

This module documents and centralises the three supported model modes:

``ModelMode.STATIC``
    Use a packaged global frequency table with no per-file adaptation.

``ModelMode.ADAPTIVE``
    Build a fresh model from the file's token stream (legacy behaviour).

``ModelMode.HYBRID``
    Start from the global table and apply sparse overrides derived from the
    file-level distribution.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "models"


class ModelMode(Enum):
    """Supported model construction modes for morphemic streams."""

    STATIC = "static"
    ADAPTIVE = "adaptive"
    HYBRID = "hybrid"

    @classmethod
    def from_string(cls, value: str) -> "ModelMode":
        try:
            return cls(value)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Unknown model mode: {value}") from exc


@dataclass(frozen=True)
class GlobalModel:
    model_id: str
    precision_bits: int
    alphabet_size: int
    frequencies: List[int]

    @property
    def total(self) -> int:
        return 1 << self.precision_bits


class GlobalModelRegistry:
    """Lazy loader for packaged global models."""

    _cache: Dict[str, GlobalModel] = {}

    @classmethod
    def load(cls, model_id: str = "global_v1") -> GlobalModel:
        if model_id in cls._cache:
            return cls._cache[model_id]
        path = _DATA_DIR / f"{model_id.replace('/', '_')}.json"
        if not path.exists():
            raise FileNotFoundError(f"Global model '{model_id}' not found at {path}")
        raw = json.loads(path.read_text())
        model = GlobalModel(
            model_id=str(raw.get("model_id", model_id)),
            precision_bits=int(raw.get("precision_bits", 12)),
            alphabet_size=int(raw.get("alphabet_size", len(raw.get("frequencies", [])))),
            frequencies=list(raw.get("frequencies", [])),
        )
        if len(model.frequencies) != model.alphabet_size:
            padded = list(model.frequencies)
            if len(padded) < model.alphabet_size:
                padded.extend([1] * (model.alphabet_size - len(padded)))
            model = GlobalModel(
                model_id=model.model_id,
                precision_bits=model.precision_bits,
                alphabet_size=model.alphabet_size,
                frequencies=padded,
            )
        cls._cache[model_id] = model
        return model


def resolve_model_mode(value: str | ModelMode | None) -> ModelMode:
    if value is None:
        return ModelMode.ADAPTIVE
    if isinstance(value, ModelMode):
        return value
    return ModelMode.from_string(str(value))


def apply_hybrid_overrides(
    base: GlobalModel, overrides: Mapping[int, int], *, alphabet_size: int | None = None
) -> List[int]:
    """Return a concrete frequency table for a hybrid model."""

    target = alphabet_size or base.alphabet_size
    frequencies = list(base.frequencies)
    if len(frequencies) < target:
        frequencies.extend([1] * (target - len(frequencies)))
    for index, freq in overrides.items():
        if index < 0:
            continue
        if index >= len(frequencies):
            frequencies.extend([1] * (index + 1 - len(frequencies)))
        frequencies[index] = int(freq)
    return frequencies


def build_sparse_overrides(
    adaptive_frequencies: Iterable[int],
    base_frequencies: Iterable[int],
    *,
    threshold: int = 0,
) -> Dict[int, int]:
    """Compute overrides from adaptive frequencies relative to a base model."""

    adaptive_list = list(adaptive_frequencies)
    base_list = list(base_frequencies)
    overrides: Dict[int, int] = {}
    for index, (adaptive, base) in enumerate(zip(adaptive_list, base_list)):
        if abs(int(adaptive) - int(base)) > threshold:
            overrides[index] = int(adaptive)
    if len(adaptive_list) > len(base_list):
        for index in range(len(base_list), len(adaptive_list)):
            overrides[index] = int(adaptive_list[index])
    return overrides


__all__ = [
    "apply_hybrid_overrides",
    "build_sparse_overrides",
    "GlobalModel",
    "GlobalModelRegistry",
    "ModelMode",
    "resolve_model_mode",
]
