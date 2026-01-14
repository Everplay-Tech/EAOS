"""Token optimisation strategies prior to entropy coding."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence


@dataclass
class TokenOptimisationPlan:
    """Mapping between original dictionary indices and dense ranks."""

    strategy: str
    dense_to_original: List[int]
    original_to_dense: Dict[int, int]

    @property
    def alphabet_size(self) -> int:
        return len(self.dense_to_original) or 1

    def apply(self, tokens: Sequence[int]) -> List[int]:
        mapper = self.original_to_dense
        return [mapper[token] for token in tokens]

    def restore(self, tokens: Sequence[int]) -> List[int]:
        palette = self.dense_to_original
        return [palette[token] for token in tokens]

    def to_metadata(self) -> Dict[str, Iterable[int]]:
        return {
            "strategy": self.strategy,
            "dense_to_original": self.dense_to_original,
        }

    @classmethod
    def from_metadata(cls, data: Dict[str, Iterable[int]]) -> "TokenOptimisationPlan":
        strategy = str(data.get("strategy", "frequency-dense"))
        dense_to_original = list(data.get("dense_to_original", []))
        original_to_dense = {original: index for index, original in enumerate(dense_to_original)}
        return cls(strategy=strategy, dense_to_original=dense_to_original, original_to_dense=original_to_dense)


def build_frequency_plan(symbols: Iterable[int], *, strategy: str = "frequency-dense") -> TokenOptimisationPlan | None:
    counter = Counter(symbols)
    if not counter:
        return None
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    dense_to_original = [symbol for symbol, _ in ordered]
    original_to_dense = {symbol: index for index, symbol in enumerate(dense_to_original)}
    return TokenOptimisationPlan(
        strategy=strategy,
        dense_to_original=dense_to_original,
        original_to_dense=original_to_dense,
    )


__all__ = ["TokenOptimisationPlan", "build_frequency_plan"]
