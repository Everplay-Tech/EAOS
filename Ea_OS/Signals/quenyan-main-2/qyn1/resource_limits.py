"""Resource budgeting helpers for decoding untrusted archives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


class ResourceBudgetExceeded(RuntimeError):
    """Raised when an archive exceeds configured resource limits."""


@dataclass(frozen=True)
class ResourceBudget:
    """Declarative limits covering decode and decompress stages."""

    max_symbols: int = 10_000_000
    max_model_bytes: int = 4_000_000
    max_compressed_bytes: int = 64_000_000
    max_string_table_bytes: int = 64_000_000
    max_payload_bytes: int = 64_000_000

    def ensure_symbols(self, count: int) -> None:
        if count > self.max_symbols:
            raise ResourceBudgetExceeded(
                f"symbol count {count} exceeds budgeted maximum {self.max_symbols}"
            )

    def ensure_compressed(self, size: int) -> None:
        if size > self.max_compressed_bytes:
            raise ResourceBudgetExceeded(
                f"compressed payload {size} bytes exceeds budgeted maximum {self.max_compressed_bytes}"
            )

    def ensure_model(self, model: Mapping[str, object]) -> None:
        # Rough heuristic: estimate serialized size by summing lengths of lists and strings
        total = 0
        for value in model.values():
            if isinstance(value, (bytes, bytearray)):
                total += len(value)
            elif isinstance(value, str):
                total += len(value.encode("utf-8"))
            elif isinstance(value, Sequence):
                total += len(value)
        if total > self.max_model_bytes:
            raise ResourceBudgetExceeded(
                f"model size {total} exceeds budgeted maximum {self.max_model_bytes}"
            )

    def ensure_string_table(self, size: int) -> None:
        if size > self.max_string_table_bytes:
            raise ResourceBudgetExceeded(
                f"string table {size} bytes exceeds budgeted maximum {self.max_string_table_bytes}"
            )

    def ensure_payload_bytes(self, size: int) -> None:
        if size > self.max_payload_bytes:
            raise ResourceBudgetExceeded(
                f"payload section {size} bytes exceeds budgeted maximum {self.max_payload_bytes}"
            )


__all__ = ["ResourceBudget", "ResourceBudgetExceeded"]
