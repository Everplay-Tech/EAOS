"""Mathematical helpers derived from open-source routines."""

from __future__ import annotations

from math import sqrt
from typing import Iterable


def fibonacci(n: int) -> int:
    """Return the n-th Fibonacci number using iterative doubling."""

    if n < 0:
        raise ValueError("n must be non-negative")
    if n in {0, 1}:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def vector_length(vector: Iterable[float]) -> float:
    """Compute the Euclidean length of an iterable of floats."""

    return sqrt(sum(component * component for component in vector))
