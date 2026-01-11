import json
import random
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Tuple

import pytest

from matrix.utils import canonical, state_hash


def _random_string(rng: random.Random, length: int) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(rng.choice(alphabet) for _ in range(length))


def _random_leaf(rng: random.Random) -> Any:
    choice = rng.random()
    if choice < 0.2:
        return rng.randint(-10_000, 10_000)
    if choice < 0.4:
        return rng.random() * rng.randint(-1000, 1000)
    if choice < 0.6:
        return bool(rng.randint(0, 1))
    if choice < 0.8:
        return None
    return _random_string(rng, rng.randint(1, 16))


def _random_payload(rng: random.Random, depth: int = 0) -> Any:
    if depth > 3:
        return _random_leaf(rng)

    choice = rng.random()
    if choice < 0.33:
        # Generate a dictionary with string keys
        size = rng.randint(1, 4)
        payload = {}
        for _ in range(size):
            key = _random_string(rng, rng.randint(1, 12))
            payload[key] = _random_payload(rng, depth + 1)
        return payload
    if choice < 0.66:
        # Generate a list with heterogeneous members
        size = rng.randint(1, 5)
        return [_random_payload(rng, depth + 1) for _ in range(size)]
    return _random_leaf(rng)


@pytest.mark.parametrize("seed", [1, 7, 42, 1337])
def test_state_hash_stable_under_concurrency(seed: int) -> None:
    rng = random.Random(seed)
    payloads: List[Any] = [_random_payload(rng) for _ in range(200)]

    expected = [state_hash(payload) for payload in payloads]

    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent = list(pool.map(state_hash, payloads))

    assert concurrent == expected

    shuffled = list(payloads)
    rng.shuffle(shuffled)

    # Re-hash the shuffled payloads and ensure the digest stays identical
    for payload, digest in zip(shuffled, expected):
        assert state_hash(payload) == digest


class _HashRegistry:
    """A lightweight LRU registry used to mimic eviction behaviour in tests."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._store: "OrderedDict[str, str]" = OrderedDict()

    def record(self, payload: Any) -> str:
        key = canonical(payload).decode("utf-8")
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]

        digest = state_hash(payload)
        if len(self._store) >= self.capacity:
            self._store.popitem(last=False)
        self._store[key] = digest
        return digest


def _snapshot_payload(payload: Any) -> Any:
    """Round-trip payloads through JSON to normalise ordering for comparisons."""

    return json.loads(canonical(payload))


def _seeded_payloads(rng: random.Random, count: int) -> List[Tuple[Any, str]]:
    payloads: List[Tuple[Any, str]] = []
    for _ in range(count):
        payload = _random_payload(rng)
        snapshot = _snapshot_payload(payload)
        payloads.append((snapshot, state_hash(snapshot)))
    return payloads


def test_registry_eviction_preserves_hash_determinism() -> None:
    rng = random.Random(2024)
    registry = _HashRegistry(capacity=64)
    catalog = _seeded_payloads(rng, 160)

    # Warm up the registry with a mix of cache hits and misses
    for _ in range(500):
        if catalog and rng.random() < 0.25:
            payload, expected = rng.choice(catalog)
        else:
            payload = _snapshot_payload(_random_payload(rng))
            expected = state_hash(payload)
            catalog.append((payload, expected))
        assert registry.record(payload) == expected

    rng.shuffle(catalog)
    sample = catalog[:40]

    # Even after numerous evictions, recomputing hashes should stay stable
    for payload, expected in sample:
        assert state_hash(payload) == expected
        assert registry.record(payload) == expected
