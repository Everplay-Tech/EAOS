"""Compression configuration profiles and presets for QYN-1 packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping


@dataclass(frozen=True)
class CompressionConfig:
    """User facing configuration options controlling the compression pipeline."""

    mode: str
    backend: str
    model_mode: str = "adaptive"
    backend_options: Mapping[str, Any] = field(default_factory=dict)
    token_optimisation: str = "local"
    shared_string_table: bool = False
    project_scope: bool = False
    description: str = ""

    def backend_kwargs(self) -> Dict[str, Any]:
        return dict(self.backend_options)

    def wants_project_planning(self) -> bool:
        return self.project_scope or self.token_optimisation == "project" or self.shared_string_table

    def with_backend(
        self, backend: str, *, backend_options: Mapping[str, Any] | None = None
    ) -> "CompressionConfig":
        return CompressionConfig(
            mode=self.mode,
            backend=backend,
            model_mode=self.model_mode,
            backend_options=backend_options if backend_options is not None else self.backend_options,
            token_optimisation=self.token_optimisation,
            shared_string_table=self.shared_string_table,
            project_scope=self.project_scope,
            description=self.description,
        )


_PRESET_MODES: Dict[str, CompressionConfig] = {
    "balanced": CompressionConfig(
        mode="balanced",
        backend="fse-production",
        model_mode="adaptive",
        backend_options={"table_log": 12},
        token_optimisation="local",
        shared_string_table=False,
        project_scope=False,
        description="Default mode balancing size and determinism.",
    ),
    "maximum": CompressionConfig(
        mode="maximum",
        backend="chunked-rans",
        model_mode="adaptive",
        backend_options={"precision_bits": 14, "chunk_size": 32768},
        token_optimisation="project",
        shared_string_table=True,
        project_scope=True,
        description="Aggressively compress using project-wide statistics.",
    ),
    "security": CompressionConfig(
        mode="security",
        backend="fse-production",
        model_mode="adaptive",
        backend_options={"table_log": 11},
        token_optimisation="none",
        shared_string_table=False,
        project_scope=False,
        description="Prioritise cryptographic isolation over compression.",
    ),
}


def get_compression_config(mode: str | None) -> CompressionConfig:
    if mode is None:
        return _PRESET_MODES["balanced"]
    try:
        return _PRESET_MODES[mode]
    except KeyError as exc:  # pragma: no cover - defensive programming
        raise ValueError(f"Unknown compression mode: {mode}") from exc


def available_modes() -> Dict[str, str]:
    return {name: config.description for name, config in _PRESET_MODES.items()}


__all__ = [
    "CompressionConfig",
    "available_modes",
    "get_compression_config",
]
