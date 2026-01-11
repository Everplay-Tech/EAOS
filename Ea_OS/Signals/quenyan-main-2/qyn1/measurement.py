from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from .compression import get_backend
from .encoder import QYNEncoder
from .event_logging import EncodingEventLog, EventPayloadClass
from .package import QYNPackage, encode_package
from .string_table import StringTable
from .token_optimisation import TokenOptimisationPlan


def entropy(counter: Counter[Any]) -> float:
    total = sum(counter.values())
    if total == 0:
        return 0.0
    entropy_bits = 0.0
    for count in counter.values():
        probability = count / total
        entropy_bits -= probability * math.log2(probability)
    return entropy_bits


def conditional_entropy(joint_counter: Counter[tuple[str, str]]) -> float:
    if not joint_counter:
        return 0.0
    totals: Counter[str] = Counter()
    for (token, _), count in joint_counter.items():
        totals[token] += count
    total_events = sum(joint_counter.values())
    entropy_bits = 0.0
    for token, token_count in totals.items():
        token_prob = token_count / total_events
        context_entropy = 0.0
        for (candidate_token, payload_key), count in joint_counter.items():
            if candidate_token != token:
                continue
            payload_prob = count / token_count
            context_entropy -= payload_prob * math.log2(payload_prob)
        entropy_bits += token_prob * context_entropy
    return entropy_bits


@dataclass
class MeasurementResult:
    event_log: EncodingEventLog
    string_table: StringTable
    package: QYNPackage
    token_entropy: float
    joint_entropy: float
    payload_conditional_entropy: Dict[str, float]
    bits_per_token: List[float]
    string_bits_per_event: List[float]
    tokens_section_bits: int
    string_table_section_bits: int
    metadata_bits: int
    model_estimated_token_bits: float


def _recover_plan(package: QYNPackage) -> TokenOptimisationPlan | None:
    extras = package.compression_extras or {}
    optimisation = extras.get("optimisation") if isinstance(extras, dict) else None
    if isinstance(optimisation, dict):
        return TokenOptimisationPlan.from_metadata(optimisation)
    return None


def _decode_tokens(package: QYNPackage) -> List[int]:
    backend = get_backend(package.compression_backend)
    return backend.decode(
        package.compressed_tokens, package.compression_model, package.symbol_count
    )


def _compute_symbol_bits(
    tokens: Iterable[int], package: QYNPackage, plan: TokenOptimisationPlan | None
) -> List[float]:
    model = package.compression_model
    backend = package.compression_backend
    backend_impl = get_backend(backend)
    symbol_list = list(tokens)
    if plan is not None:
        symbol_list = plan.restore(symbol_list)
    bits: List[float] = []
    if backend == "chunked-rans":
        chunk_meta = model.get("chunks", []) if isinstance(model, dict) else []
        cursor = 0
        for entry in chunk_meta:
            frequencies = list(entry.get("frequencies", []))
            symbol_count = int(entry.get("symbol_count", 0))
            total = sum(frequencies) or 1
            for symbol in symbol_list[cursor : cursor + symbol_count]:
                freq = frequencies[symbol] if symbol < len(frequencies) else 0
                bits.append(math.log2(total / max(1, freq)))
            cursor += symbol_count
        return bits
    frequencies = None
    if isinstance(model, dict) and model.get("mode") in {"static", "hybrid"}:
        try:
            table = backend_impl.table_from_model(model)  # type: ignore[assignment]
            frequencies = list(table.frequencies)
        except Exception:
            frequencies = None
    if isinstance(model, dict):
        frequencies = model.get("frequencies") or model.get("counts")
    if isinstance(frequencies, list) and frequencies:
        total = sum(int(value) for value in frequencies) or 1
        for symbol in symbol_list:
            freq = frequencies[symbol] if symbol < len(frequencies) else 0
            bits.append(math.log2(total / max(1, int(freq))))
    else:
        bits = [0.0 for _ in symbol_list]
    return bits


def _string_bits_for_events(
    event_log: EncodingEventLog, string_table: StringTable, string_table_bits: int
) -> List[float]:
    if not string_table:
        return [0.0 for _ in event_log.events]
    per_entry = string_table_bits / max(len(string_table), 1)
    usage = Counter(event.string_index for event in event_log.events if event.string_index is not None)
    allocation: List[float] = []
    for event in event_log.events:
        if event.string_index is None:
            allocation.append(0.0)
            continue
        count = usage.get(event.string_index, 1)
        allocation.append(per_entry / max(count, 1))
    return allocation


def build_measurement_from_source(
    source: str,
    *,
    file_id: str = "unknown",
    encoder: Optional[QYNEncoder] = None,
) -> MeasurementResult:
    active_encoder = encoder or QYNEncoder()
    event_log = EncodingEventLog(file_id)
    stream = active_encoder.encode(source, event_log=event_log)
    package = encode_package(stream)
    string_table = StringTable.from_bytes(package.string_table_bytes)
    event_log.attach_string_table(string_table)
    event_log.finalize()

    token_counter = Counter(event_log.token_keys)
    token_entropy = entropy(token_counter)

    joint_counter: Counter[tuple[str, tuple[str, str | None, str | None]]] = Counter(
        (event.token_key, event.payload_key()) for event in event_log.events
    )
    joint_entropy = entropy(joint_counter)

    conditional: Dict[str, float] = {}
    for payload_class in EventPayloadClass:
        class_events = [event for event in event_log.events if event.payload_class == payload_class]
        if not class_events:
            conditional[payload_class.value] = 0.0
            continue
        class_counter: Counter[tuple[str, str]] = Counter()
        for event in class_events:
            payload_id = json.dumps(event.payload_key(), sort_keys=True)
            class_counter[(event.token_key, payload_id)] += 1
        conditional[payload_class.value] = conditional_entropy(class_counter)

    plan = _recover_plan(package)
    decoded_tokens = _decode_tokens(package)
    bits_per_token = _compute_symbol_bits(decoded_tokens, package, plan)
    tokens_section_bits = (4 + len(package.compressed_tokens)) * 8
    string_table_section_bits = (4 + len(package.string_table_bytes)) * 8
    metadata_payload = json.dumps(package.metadata.to_dict(), sort_keys=True).encode("utf-8")
    metadata_bits = (4 + len(metadata_payload)) * 8
    model_estimated_token_bits = sum(bits_per_token)

    string_bits_per_event = _string_bits_for_events(
        event_log, string_table, string_table_section_bits
    )

    return MeasurementResult(
        event_log=event_log,
        string_table=string_table,
        package=package,
        token_entropy=token_entropy,
        joint_entropy=joint_entropy,
        payload_conditional_entropy=conditional,
        bits_per_token=bits_per_token,
        string_bits_per_event=string_bits_per_event,
        tokens_section_bits=tokens_section_bits,
        string_table_section_bits=string_table_section_bits,
        metadata_bits=metadata_bits,
        model_estimated_token_bits=model_estimated_token_bits,
    )


__all__ = [
    "MeasurementResult",
    "build_measurement_from_source",
    "conditional_entropy",
    "entropy",
]
