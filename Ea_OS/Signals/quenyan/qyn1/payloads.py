from __future__ import annotations

import base64
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .compression import RANSBackend
from .string_table import StringTable


@dataclass
class Payload:
    """Auxiliary payload emitted alongside the morphemic stream."""

    type: str
    value: Any


@dataclass
class PayloadChannelEntry:
    type: str
    channel: str
    kind: Optional[str] = None
    token_index: Optional[int] = None


@dataclass
class PayloadChannels:
    """Channelised payload streams aligned with the morphemic grammar."""

    entries: List[PayloadChannelEntry] = field(default_factory=list)
    identifiers: List[Any] = field(default_factory=list)
    strings: List[Any] = field(default_factory=list)
    numbers: List[Any] = field(default_factory=list)
    counts: List[Any] = field(default_factory=list)
    flags: List[Any] = field(default_factory=list)
    structured: List[Any] = field(default_factory=list)
    token_keys: Optional[List[str]] = None

    @property
    def identifier_indices(self) -> List[Any]:
        """Alias retained for backward compatibility with older test helpers."""

        return self.identifiers

    # ------------------------------------------------------------------
    # Construction helpers

    def append(
        self,
        payload_type: str,
        channel: str,
        value: Any,
        *,
        kind: Optional[str] = None,
        token_index: Optional[int] = None,
    ) -> None:
        self.entries.append(PayloadChannelEntry(payload_type, channel, kind, token_index))
        if channel == "I":
            self.identifiers.append(value)
        elif channel == "S":
            self.strings.append(value)
        elif channel == "N":
            self.numbers.append(value)
        elif channel == "C":
            self.counts.append(value)
        elif channel == "F":
            self.flags.append(value)
        else:
            self.structured.append(value)

    def append_identifier(
        self,
        payload_type: str,
        value: Any,
        *,
        kind: Optional[str] = None,
        token_index: Optional[int] = None,
    ) -> None:
        self.append(payload_type, "I", value, kind=kind, token_index=token_index)

    def append_string(
        self,
        payload_type: str,
        value: Any,
        *,
        kind: Optional[str] = None,
        token_index: Optional[int] = None,
    ) -> None:
        self.append(payload_type, "S", value, kind=kind, token_index=token_index)

    def append_number(
        self,
        payload_type: str,
        value: Any,
        *,
        kind: Optional[str] = None,
        token_index: Optional[int] = None,
    ) -> None:
        self.append(payload_type, "N", value, kind=kind, token_index=token_index)

    def append_count(
        self,
        payload_type: str,
        value: Any,
        *,
        kind: Optional[str] = None,
        token_index: Optional[int] = None,
    ) -> None:
        self.append(payload_type, "C", value, kind=kind, token_index=token_index)

    def append_flag(
        self,
        payload_type: str,
        value: Any,
        *,
        kind: Optional[str] = None,
        token_index: Optional[int] = None,
    ) -> None:
        self.append(payload_type, "F", value, kind=kind, token_index=token_index)

    def append_structured(
        self,
        payload_type: str,
        value: Any,
        *,
        kind: Optional[str] = None,
        token_index: Optional[int] = None,
    ) -> None:
        self.append(payload_type, "R", value, kind=kind, token_index=token_index)

    @classmethod
    def from_payloads(cls, payloads: Iterable[Payload]) -> "PayloadChannels":
        channels = cls()
        identifier_types = {
            "function_name",
            "call_keyword_name",
            "attribute_name",
            "identifier_name",
            "parameter_name",
        }
        count_types = {
            "module_body_length",
            "assign_target_count",
            "call_arg_count",
            "call_keyword_count",
            "function_arg_count",
            "function_body_length",
            "function_async",
            "return_has_value",
            "identifier_ctx",
        }

        for payload in payloads:
            if payload.type in identifier_types:
                channels.append_identifier(payload.type, payload.value)
                continue
            if payload.type in count_types:
                channels.append_count(payload.type, int(payload.value))
                continue
            if payload.type == "literal" and isinstance(payload.value, dict):
                kind = payload.value.get("kind")
                literal_value = payload.value.get("value")
                if isinstance(literal_value, str):
                    channels.append_string(payload.type, literal_value, kind=str(kind))
                    continue
                if isinstance(literal_value, bool):
                    channels.append_count(payload.type, int(literal_value), kind=str(kind))
                    continue
                if isinstance(literal_value, int):
                    channels.append_number(payload.type, literal_value, kind=str(kind))
                    continue
            if isinstance(payload.value, str):
                channels.append_string(payload.type, payload.value)
            elif isinstance(payload.value, (int, bool)):
                channels.append_count(payload.type, int(payload.value))
            else:
                channels.append_structured(payload.type, payload.value)
        return channels

    @classmethod
    def build(cls, payloads: List[Payload], string_table: StringTable) -> "PayloadChannels":
        channels = cls()
        identifier_types = {
            "function_name",
            "call_keyword_name",
            "attribute_name",
            "identifier_name",
            "parameter_name",
        }
        count_types = {
            "module_body_length",
            "assign_target_count",
            "call_arg_count",
            "call_keyword_count",
            "function_arg_count",
            "function_body_length",
            "identifier_ctx",
        }
        flag_types = {"function_async", "return_has_value"}

        for payload in payloads:
            if payload.type in identifier_types and isinstance(payload.value, str):
                channels.append_identifier(payload.type, string_table.index_for(payload.value))
                continue
            if payload.type in count_types and isinstance(payload.value, (int, bool)):
                channels.append_count(payload.type, int(payload.value))
                continue
            if payload.type in flag_types and isinstance(payload.value, (int, bool)):
                channels.append_flag(payload.type, int(bool(payload.value)))
                continue
            if payload.type == "literal" and isinstance(payload.value, dict):
                kind = payload.value.get("kind")
                literal_value = payload.value.get("value")
                if isinstance(literal_value, str):
                    channels.append_string(
                        payload.type,
                        string_table.index_for(literal_value),
                        kind=str(kind) if kind else None,
                    )
                    continue
                if isinstance(literal_value, bool):
                    channels.append_count(
                        payload.type,
                        int(literal_value),
                        kind=str(kind) if kind else None,
                    )
                    continue
                if isinstance(literal_value, int):
                    channels.append_number(
                        payload.type,
                        int(literal_value),
                        kind=str(kind) if kind else None,
                    )
                    continue
            if isinstance(payload.value, str):
                channels.append_string(payload.type, string_table.index_for(payload.value))
            elif isinstance(payload.value, bool):
                channels.append_flag(payload.type, int(payload.value))
            elif isinstance(payload.value, int):
                channels.append_count(payload.type, int(payload.value))
            else:
                encoded = string_table.encode_payload(payload)
                channels.append_structured(payload.type, encoded)
        return channels

    def apply_token_indices(self, entries: Sequence[PayloadChannelEntry]) -> "PayloadChannels":
        if len(entries) != len(self.entries):
            return self
        for target, source in zip(self.entries, entries):
            target.token_index = source.token_index
        return self

    def to_serializable(self, *, token_keys: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        token_context = list(token_keys) if token_keys is not None else self.token_keys
        return {
            "entries": [entry.__dict__ for entry in self.entries],
            "channels": {
                "I": _encode_identifier_channel(
                    self.identifiers,
                    self.entries,
                    channel="I",
                    token_keys=token_context,
                ),
                "S": _encode_identifier_channel(self.strings, self.entries, channel="S"),
                "N": _encode_number_channel(self.numbers, self.entries),
                "C": _encode_count_channel(self.counts, self.entries),
                "F": _encode_flag_channel(self.flags),
                "R": {"payloads": self.structured},
            },
        }

    @classmethod
    def from_serializable(
        cls,
        data: Dict[str, Any],
        string_table: StringTable,
        *,
        token_keys: Optional[Sequence[str]] = None,
    ) -> "PayloadChannels":
        raw_entries = data.get("entries")
        if not isinstance(raw_entries, list):
            raise ValueError("payload entries must be a list")
        entries: List[PayloadChannelEntry] = []
        for item in raw_entries:
            if not isinstance(item, dict):
                raise ValueError("payload entries must be objects")
            entry_data = dict(item)
            entry_data.setdefault("token_index", None)
            entries.append(PayloadChannelEntry(**entry_data))
        raw_channels = data.get("channels", {})
        if not isinstance(raw_channels, dict):
            raise ValueError("payload channels must be an object")
        identifiers = _decode_identifier_channel(
            raw_channels.get("I", {}),
            entries,
            channel="I",
            token_keys=token_keys,
        )
        strings = _decode_identifier_channel(raw_channels.get("S", {}), entries, channel="S")
        numbers = _decode_number_channel(raw_channels.get("N", {}), entries)
        counts = _decode_count_channel(raw_channels.get("C", {}), entries)
        flags = _decode_flag_channel(raw_channels.get("F", {}))
        structured_section = raw_channels.get("R", {})
        structured_payloads: List[Dict[str, Any]] = []
        if structured_section:
            if not isinstance(structured_section, dict):
                raise ValueError("structured channel must be an object")
            payloads = structured_section.get("payloads", [])
            if not isinstance(payloads, list):
                raise ValueError("structured payloads must be a list")
            structured_payloads = [string_table.decode_payload(p) for p in payloads]
        return cls(
            entries=entries,
            identifiers=list(identifiers),
            strings=list(strings),
            numbers=list(numbers),
            counts=list(counts),
            flags=list(flags),
            structured=structured_payloads,
            token_keys=list(token_keys) if token_keys is not None else None,
        )

    # ------------------------------------------------------------------
    # Consumption helpers

    def cursor(self) -> "PayloadCursor":
        return PayloadCursor(self)

    def to_payloads(self, string_table: Optional[StringTable] = None) -> List[Payload]:
        payloads: List[Payload] = []
        cursor = self.cursor()
        for entry in self.entries:
            raw_value = cursor.consume(entry.type, entry.channel, kind=entry.kind)
            value = raw_value
            if string_table is not None and entry.channel in {"I", "S"}:
                if isinstance(raw_value, int):
                    value = string_table.string_for_index(raw_value)
            if (
                entry.channel == "R"
                and isinstance(value, dict)
                and set(value.keys()) == {"type", "value"}
                and value.get("type") == entry.type
            ):
                value = value.get("value")
            if entry.kind is not None:
                payloads.append(Payload(entry.type, {"kind": entry.kind, "value": value}))
            else:
                payloads.append(Payload(entry.type, value))
        return payloads


class PayloadCursor:
    """Iterator that replays payload channels in grammar order.

    The cursor prefers to validate against the recorded :class:`PayloadChannelEntry`
    sequence when available, but it can also operate purely from the per-channel
    streams. This keeps decoding deterministic even when the entry stream is
    omitted and the grammar alone dictates which payload channel to consume.
    """

    def __init__(self, channels: PayloadChannels):
        self._entry_iter: Iterator[PayloadChannelEntry] | None = None
        if channels.entries:
            self._entry_iter = iter(channels.entries)
        self._identifier_iter: Iterator[Any] = iter(channels.identifiers)
        self._string_iter: Iterator[Any] = iter(channels.strings)
        self._number_iter: Iterator[Any] = iter(channels.numbers)
        self._count_iter: Iterator[Any] = iter(channels.counts)
        self._flag_iter: Iterator[Any] = iter(channels.flags)
        self._structured_iter: Iterator[Any] = iter(channels.structured)

    def _consume_channel(self, channel: str) -> Any:
        try:
            if channel == "I":
                return next(self._identifier_iter)
            if channel == "S":
                return next(self._string_iter)
            if channel == "N":
                return next(self._number_iter)
            if channel == "C":
                return next(self._count_iter)
            if channel == "F":
                return next(self._flag_iter)
            return next(self._structured_iter)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise ValueError("payload channel exhausted early") from exc

    def consume_with_entry(
        self,
        expected_type: str,
        expected_channel: Optional[str] = None,
        *,
        kind: Optional[str] = None,
    ) -> tuple[PayloadChannelEntry, Any]:
        if self._entry_iter is None:
            if expected_channel is None:
                raise ValueError(
                    "payload channel must be specified when the entry stream is absent"
                )
            entry = PayloadChannelEntry(expected_type, expected_channel, kind)
            return entry, self._consume_channel(expected_channel)

        try:
            entry = next(self._entry_iter)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise ValueError("payload stream exhausted early") from exc
        if entry.type != expected_type:
            raise ValueError(
                f"Expected payload {expected_type!r} but found {entry.type!r}"
            )
        if expected_channel is None:
            expected_channel = entry.channel
        if entry.channel != expected_channel:
            raise ValueError(
                f"Payload channel mismatch: expected {expected_channel!r} but found {entry.channel!r}"
            )
        if entry.kind is not None and kind is not None and entry.kind != kind:
            raise ValueError(
                f"Payload kind mismatch: expected {kind!r} but found {entry.kind!r}"
            )
        return entry, self._consume_channel(expected_channel)

    def consume(self, expected_type: str, expected_channel: str, *, kind: Optional[str] = None) -> Any:
        entry, value = self.consume_with_entry(expected_type, expected_channel, kind=kind)
        return value


def _partition_symbols_by_slot(
    symbols: Sequence[int], entries: Sequence[PayloadChannelEntry], channel: str
) -> Optional[Dict[Tuple[str, Optional[str]], List[int]]]:
    if not entries:
        return None

    grouped: Dict[Tuple[str, Optional[str]], List[int]] = {}
    iterator = iter(symbols)
    consumed = 0
    for entry in entries:
        if entry.channel != channel:
            continue
        try:
            symbol = next(iterator)
        except StopIteration as exc:
            raise ValueError("payload channel has fewer symbols than grammar slots") from exc
        slot_key = (entry.type, entry.kind)
        grouped.setdefault(slot_key, []).append(symbol)
        consumed += 1

    try:
        next(iterator)
        raise ValueError("payload channel has more symbols than grammar slots")
    except StopIteration:
        pass

    return grouped if consumed else None


def _encode_slot_conditioned_channel(
    symbols: Sequence[int],
    entries: Sequence[PayloadChannelEntry],
    *,
    channel: str,
    encoder: Callable[[Sequence[int]], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    grouped = _partition_symbols_by_slot(symbols, entries, channel)
    if not grouped:
        return None

    slots: List[Dict[str, Any]] = []
    for (slot_type, slot_kind), slot_symbols in grouped.items():
        slots.append(
            {
                "type": slot_type,
                "kind": slot_kind,
                "stream": encoder(slot_symbols),
            }
        )

    return {
        "mode": "slot-conditioned",
        "symbol_count": len(symbols),
        "slots": slots,
    }


def _token_context_resolver(
    token_keys: Optional[Sequence[str]],
) -> Optional[Callable[[PayloadChannelEntry], Optional[str]]]:
    if not token_keys:
        return None
    valid_keys = list(token_keys)

    def resolver(entry: PayloadChannelEntry) -> Optional[str]:
        if entry.token_index is None:
            return None
        if entry.token_index < 0 or entry.token_index >= len(valid_keys):
            return None
        token_key = valid_keys[entry.token_index]
        if not isinstance(token_key, str):
            return None
        if token_key.startswith(("op:", "construct:", "flow:", "structure:")):
            return token_key
        return None

    return resolver


def _encode_context_conditioned_channel(
    symbols: Sequence[int],
    entries: Sequence[PayloadChannelEntry],
    *,
    channel: str,
    encoder: Callable[[Sequence[int]], Dict[str, Any]],
    context_resolver: Optional[Callable[[PayloadChannelEntry], Optional[str]]],
) -> Optional[Dict[str, Any]]:
    if context_resolver is None:
        return None
    grouped: Dict[Optional[str], List[int]] = {}
    iterator = iter(symbols)
    for entry in entries:
        if entry.channel != channel:
            continue
        try:
            symbol = next(iterator)
        except StopIteration as exc:
            raise ValueError("payload channel has fewer symbols than grammar slots") from exc
        context_key = context_resolver(entry)
        grouped.setdefault(context_key, []).append(symbol)

    try:
        next(iterator)
        raise ValueError("payload channel has more symbols than grammar slots")
    except StopIteration:
        pass

    if not grouped:
        return None
    if len(grouped) == 1 and None in grouped:
        return None

    contexts: List[Dict[str, Any]] = []
    for context_key, context_symbols in grouped.items():
        contexts.append(
            {
                "context": context_key,
                "stream": encoder(context_symbols),
            }
        )

    return {
        "mode": "token-context",
        "symbol_count": len(symbols),
        "contexts": contexts,
    }


def _decode_slot_conditioned_channel(
    channel_data: Dict[str, Any],
    entries: Sequence[PayloadChannelEntry],
    *,
    channel: str,
    decoder: Callable[[Dict[str, Any]], List[int]],
) -> Optional[List[int]]:
    if (
        not entries
        or not isinstance(channel_data, dict)
        or channel_data.get("mode") != "slot-conditioned"
    ):
        return None

    raw_slots = channel_data.get("slots")
    if not isinstance(raw_slots, list):
        raise ValueError("slot-conditioned channels must declare a slots array")

    decoded: Dict[Tuple[str, Optional[str]], deque[int]] = {}
    for slot in raw_slots:
        if not isinstance(slot, dict):
            raise ValueError("slot-conditioned entries must be objects")
        slot_type = slot.get("type")
        if slot_type is None:
            raise ValueError("slot-conditioned entries require a type")
        slot_kind = slot.get("kind")
        stream = slot.get("stream", {})
        decoded[(slot_type, slot_kind)] = deque(decoder(stream))

    symbols: List[int] = []
    for entry in entries:
        if entry.channel != channel:
            continue
        key = (entry.type, entry.kind)
        stream = decoded.get(key)
        if stream is None:
            raise ValueError(f"slot-conditioned channel missing stream for {key!r}")
        if not stream:
            raise ValueError(f"slot-conditioned stream for {key!r} exhausted early")
        symbols.append(stream.popleft())

    for key, remaining in decoded.items():
        if remaining:
            raise ValueError(f"slot-conditioned stream for {key!r} contains surplus symbols")

    return symbols


def _decode_context_conditioned_channel(
    channel_data: Dict[str, Any],
    entries: Sequence[PayloadChannelEntry],
    *,
    channel: str,
    decoder: Callable[[Dict[str, Any]], List[int]],
    context_resolver: Optional[Callable[[PayloadChannelEntry], Optional[str]]],
) -> Optional[List[int]]:
    if (
        not entries
        or context_resolver is None
        or not isinstance(channel_data, dict)
        or channel_data.get("mode") != "token-context"
    ):
        return None

    raw_contexts = channel_data.get("contexts")
    if not isinstance(raw_contexts, list):
        raise ValueError("token-context channels must declare a contexts array")

    decoded: Dict[Optional[str], deque[int]] = {}
    for entry in raw_contexts:
        if not isinstance(entry, dict):
            raise ValueError("token-context entries must be objects")
        context_key = entry.get("context")
        stream = entry.get("stream", {})
        decoded[context_key] = deque(decoder(stream))

    symbols: List[int] = []
    for entry in entries:
        if entry.channel != channel:
            continue
        context_key = context_resolver(entry)
        stream = decoded.get(context_key) if context_key in decoded else decoded.get(None)
        if stream is None:
            raise ValueError(f"token-context stream missing for context {context_key!r}")
        if not stream:
            raise ValueError(f"token-context stream for {context_key!r} exhausted early")
        symbols.append(stream.popleft())

    for key, remaining in decoded.items():
        if remaining:
            raise ValueError(f"token-context stream for {key!r} contains surplus symbols")

    return symbols


def _encode_identifier_stream(symbols: List[int]) -> Dict[str, Any]:
    if not symbols:
        return _empty_channel()
    alphabet_size = max(symbols) + 1
    prior_model = {"type": "zipf", "exponent": 1.0}
    prior = _resolve_prior_weights(alphabet_size, prior_model)
    return _encode_symbol_channel(
        symbols,
        alphabet_size=alphabet_size,
        prior=prior,
        model_type="zipf",
        prior_model=prior_model,
        mode="static-adaptive",
    )


def _encode_identifier_channel(
    symbols: List[int],
    entries: Optional[Sequence[PayloadChannelEntry]] = None,
    *,
    channel: str = "I",
    token_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    context_conditioned = _encode_context_conditioned_channel(
        symbols,
        entries or [],
        channel=channel,
        encoder=_encode_identifier_stream,
        context_resolver=_token_context_resolver(token_keys),
    )
    if context_conditioned is not None:
        return context_conditioned
    slot_conditioned = _encode_slot_conditioned_channel(
        symbols,
        entries or [],
        channel=channel,
        encoder=_encode_identifier_stream,
    )
    if slot_conditioned is not None:
        return slot_conditioned
    return _encode_identifier_stream(symbols)


def _decode_identifier_stream(channel: Dict[str, Any]) -> List[int]:
    return _decode_symbol_channel(channel)


def _decode_identifier_channel(
    channel_data: Dict[str, Any],
    entries: Optional[Sequence[PayloadChannelEntry]] = None,
    *,
    channel: str = "I",
    token_keys: Optional[Sequence[str]] = None,
) -> List[int]:
    context_conditioned = _decode_context_conditioned_channel(
        channel_data,
        entries or [],
        channel=channel,
        decoder=_decode_identifier_stream,
        context_resolver=_token_context_resolver(token_keys),
    )
    if context_conditioned is not None:
        return context_conditioned
    slot_conditioned = _decode_slot_conditioned_channel(
        channel_data,
        entries or [],
        channel=channel,
        decoder=_decode_identifier_stream,
    )
    if slot_conditioned is not None:
        return slot_conditioned
    return _decode_identifier_stream(channel_data)


def _encode_count_stream(symbols: List[int]) -> Dict[str, Any]:
    if not symbols:
        return _empty_channel()
    alphabet_size = max(symbols) + 1
    prior_model = {"type": "geometric", "alpha": 0.45}
    prior = _resolve_prior_weights(alphabet_size, prior_model)
    return _encode_symbol_channel(
        symbols,
        alphabet_size=alphabet_size,
        prior=prior,
        model_type="geometric-count",
        prior_model=prior_model,
        mode="static-adaptive",
    )


def _encode_count_channel(
    symbols: List[int], entries: Optional[Sequence[PayloadChannelEntry]] = None
) -> Dict[str, Any]:
    slot_conditioned = _encode_slot_conditioned_channel(
        symbols,
        entries or [],
        channel="C",
        encoder=_encode_count_stream,
    )
    if slot_conditioned is not None:
        return slot_conditioned
    return _encode_count_stream(symbols)


def _decode_count_stream(channel: Dict[str, Any]) -> List[int]:
    return _decode_symbol_channel(channel)


def _decode_count_channel(
    channel_data: Dict[str, Any], entries: Optional[Sequence[PayloadChannelEntry]] = None
) -> List[int]:
    slot_conditioned = _decode_slot_conditioned_channel(
        channel_data, entries or [], channel="C", decoder=_decode_count_stream
    )
    if slot_conditioned is not None:
        return slot_conditioned
    return _decode_count_stream(channel_data)


def _encode_flag_channel(symbols: List[int]) -> Dict[str, Any]:
    if not symbols:
        return _empty_channel(model_type="bernoulian")
    prior = [0.5, 0.5]
    return _encode_symbol_channel(symbols, alphabet_size=2, prior=prior, model_type="bernoulian")


def _decode_flag_channel(channel: Dict[str, Any]) -> List[int]:
    return _decode_symbol_channel(channel)


def _encode_number_stream(numbers: List[int]) -> Dict[str, Any]:
    if not numbers:
        return {
            "encoder": "log_magnitude_v1",
            "symbol_count": 0,
            "streams": {"zero": _empty_channel(), "sign": _empty_channel(), "bucket": _empty_channel()},
            "residuals": {"data": "", "bit_length": 0},
            "max_bucket": 0,
        }
    zero_flags = [1 if value == 0 else 0 for value in numbers]
    non_zero_values = [value for value in numbers if value != 0]
    magnitudes = [abs(value) for value in non_zero_values]
    signs = [1 if value < 0 else 0 for value in non_zero_values]
    buckets = [int(math.log2(m)) if m > 0 else 0 for m in magnitudes]
    residuals = [m - (1 << bucket) if bucket >= 0 else 0 for m, bucket in zip(magnitudes, buckets)]
    max_bucket = max(buckets, default=0)

    zero_prior_model = {"type": "bernoulli", "weights": [0.72, 0.28]}
    zero_stream = _encode_symbol_channel(
        zero_flags,
        alphabet_size=2,
        prior=_resolve_prior_weights(2, zero_prior_model),
        model_type="zero-mask",
        prior_model=zero_prior_model,
        mode="static-adaptive",
    )
    sign_prior_model = {"type": "bernoulli", "weights": [0.9, 0.1]}
    sign_stream = _encode_symbol_channel(
        signs,
        alphabet_size=2,
        prior=_resolve_prior_weights(2, sign_prior_model),
        model_type="sign",
        prior_model=sign_prior_model,
        mode="static-adaptive",
    )
    bucket_prior_model = {"type": "geometric", "alpha": 0.4}
    bucket_stream = _encode_symbol_channel(
        buckets,
        alphabet_size=max_bucket + 1,
        prior=_resolve_prior_weights(max_bucket + 1, bucket_prior_model),
        model_type="log-bucket",
        prior_model=bucket_prior_model,
        mode="static-adaptive",
    )
    residual_blob, residual_bits = _pack_residuals(residuals, buckets)
    return {
        "encoder": "log_magnitude_v1",
        "symbol_count": len(numbers),
        "streams": {
            "zero": zero_stream,
            "sign": sign_stream,
            "bucket": bucket_stream,
        },
        "residuals": {"data": residual_blob, "bit_length": residual_bits},
        "max_bucket": max_bucket,
    }


def _numeric_role(entry: PayloadChannelEntry) -> str:
    if entry.kind:
        kind = entry.kind.lower()
        if "int" in kind or "number" in kind:
            return "literal_int"
    if "index" in entry.type:
        return "index"
    if "offset" in entry.type:
        return "offset"
    if "count" in entry.type:
        return "count"
    return "number"


def _encode_number_roles(numbers: List[int], entries: Sequence[PayloadChannelEntry]) -> Dict[str, Any]:
    if len(numbers) != len(entries):
        return _encode_number_stream(numbers)
    roles = [_numeric_role(entry) for entry in entries]
    role_streams: Dict[str, List[int]] = {}
    for value, role in zip(numbers, roles):
        role_streams.setdefault(role, []).append(value)
    encoded_streams = {role: _encode_number_stream(values) for role, values in role_streams.items()}
    return {
        "encoder": "role_buckets_v1",
        "symbol_count": len(numbers),
        "roles": encoded_streams,
        "role_index": roles,
    }


def _encode_number_channel(
    numbers: List[int], entries: Optional[Sequence[PayloadChannelEntry]] = None
) -> Dict[str, Any]:
    if entries:
        return _encode_number_roles(numbers, entries)
    return _encode_number_stream(numbers)


def _decode_number_stream(channel: Dict[str, Any]) -> List[int]:
    if not channel:
        return []
    encoder = channel.get("encoder")
    if encoder == "role_buckets_v1":
        return _decode_number_roles(channel)
    if encoder != "log_magnitude_v1":
        return _decode_symbol_channel(channel)

    symbol_count = int(channel.get("symbol_count", 0))
    streams = channel.get("streams", {})
    zero_stream = streams.get("zero", {}) if isinstance(streams, dict) else {}
    sign_stream = streams.get("sign", {}) if isinstance(streams, dict) else {}
    bucket_stream = streams.get("bucket", {}) if isinstance(streams, dict) else {}

    zero_flags = _decode_symbol_channel(zero_stream)
    if len(zero_flags) != symbol_count:
        raise ValueError("zero-mask length does not match symbol count")
    non_zero_count = symbol_count - sum(zero_flags)
    signs = _decode_symbol_channel(sign_stream) if non_zero_count else []
    buckets = _decode_symbol_channel(bucket_stream) if non_zero_count else []
    if non_zero_count and (len(signs) != non_zero_count or len(buckets) != non_zero_count):
        raise ValueError("non-zero payload streams have inconsistent lengths")

    residual_info = channel.get("residuals", {}) if isinstance(channel, dict) else {}
    residual_blob = ""
    residual_bits = 0
    if isinstance(residual_info, dict):
        residual_blob = str(residual_info.get("data", ""))
        residual_bits = int(residual_info.get("bit_length", 0))
    residuals = _unpack_residuals(residual_blob, residual_bits, buckets)
    if residuals and len(residuals) != len(buckets):
        raise ValueError("residual stream length mismatch")

    numbers: List[int] = []
    sign_index = 0
    bucket_index = 0
    residual_index = 0
    for flag in zero_flags:
        if flag:
            numbers.append(0)
            continue
        bucket = buckets[bucket_index]
        sign = signs[sign_index] if sign_index < len(signs) else 0
        residual = residuals[residual_index] if residual_index < len(residuals) else 0
        magnitude = (1 << bucket) + residual
        numbers.append(-magnitude if sign else magnitude)
        sign_index += 1
        bucket_index += 1
        residual_index += 1
    return numbers


def _decode_number_roles(channel: Dict[str, Any]) -> List[int]:
    symbol_count = int(channel.get("symbol_count", 0))
    roles = channel.get("role_index", []) if isinstance(channel, dict) else []
    if symbol_count and len(roles) != symbol_count:
        raise ValueError("role index length does not match symbol count")
    role_streams = channel.get("roles", {}) if isinstance(channel, dict) else {}
    decoded: Dict[str, List[int]] = {}
    for role, payload in role_streams.items():
        decoded[role] = _decode_number_stream(payload)
    positions: Dict[str, int] = {}
    numbers: List[int] = []
    for role in roles:
        stream = decoded.get(role, [])
        position = positions.get(role, 0)
        if position >= len(stream):
            raise ValueError("role stream exhausted early")
        numbers.append(stream[position])
        positions[role] = position + 1
    if symbol_count and len(numbers) != symbol_count:
        raise ValueError("decoded role buckets do not match symbol count")
    return numbers


def _decode_number_channel(
    channel: Dict[str, Any], entries: Optional[Sequence[PayloadChannelEntry]] = None
) -> List[int]:
    if channel.get("encoder") == "role_buckets_v1":
        return _decode_number_stream(channel)
    slot_conditioned = _decode_slot_conditioned_channel(
        channel,
        entries or [],
        channel="N",
        decoder=_decode_number_stream,
    )
    if slot_conditioned is not None:
        return slot_conditioned
    return _decode_number_stream(channel)


def _encode_symbol_channel(
    symbols: Sequence[int],
    *,
    alphabet_size: Optional[int] = None,
    prior: Optional[Sequence[float]] = None,
    model_type: str = "adaptive",
    precision_bits: int = 12,
    prior_model: Optional[Dict[str, Any]] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    if not symbols:
        return _empty_channel(
            precision_bits=precision_bits,
            model_type=model_type,
            alphabet_size=alphabet_size or 0,
            prior_model=prior_model,
            mode=mode,
        )

    effective_alphabet = alphabet_size if alphabet_size is not None else (max(symbols) + 1)
    required_precision = max(precision_bits, (effective_alphabet - 1).bit_length())
    precision_bits = required_precision if effective_alphabet > (1 << precision_bits) else precision_bits
    weights = _initial_weights(effective_alphabet, prior)
    for symbol in symbols:
        if symbol >= effective_alphabet:
            raise ValueError("symbol exceeds alphabet size for channel")
        weights[symbol] += 1.0
    frequencies = _normalise_weights(weights, precision_bits)

    hybrid_baseline: Optional[List[int]] = None
    if mode == "static-adaptive":
        prior_weights = _resolve_prior_weights(effective_alphabet, prior_model)
        hybrid_baseline = _normalise_weights(
            _initial_weights(effective_alphabet, prior_weights), precision_bits
        )
        if len(hybrid_baseline) != len(frequencies):
            raise ValueError("static-adaptive baseline must align with adaptive model")

    model = {
        "precision_bits": precision_bits,
        "frequencies": frequencies,
        "model_type": model_type,
    }

    if mode == "static-adaptive":
        delta = [freq - base for freq, base in zip(frequencies, hybrid_baseline or [])]
        model.update(
            {
                "mode": mode,
                "prior_model": prior_model or {},
                "delta": delta,
            }
        )

    backend = RANSBackend(precision_bits=precision_bits)
    compressed = backend.encode(list(symbols), model)
    return {
        "symbol_count": len(symbols),
        "alphabet_size": effective_alphabet,
        "model": model,
        "data": base64.b64encode(compressed).decode("ascii"),
    }


def _decode_symbol_channel(channel: Dict[str, Any]) -> List[int]:
    symbol_count = int(channel.get("symbol_count", 0))
    if symbol_count == 0:
        return []
    model = channel.get("model")
    if not isinstance(model, dict):
        raise ValueError("channel model must be a dictionary")
    precision_bits = int(model.get("precision_bits", 12))
    mode = model.get("mode")
    if mode == "static-adaptive":
        prior_model = model.get("prior_model")
        alphabet_size = int(channel.get("alphabet_size", 0) or len(model.get("delta", [])))
        if alphabet_size <= 0:
            alphabet_size = len(model.get("frequencies", []))
        if alphabet_size <= 0:
            raise ValueError("static-adaptive channels require a positive alphabet size")
        prior_weights = _resolve_prior_weights(alphabet_size, prior_model)
        baseline = _normalise_weights(
            _initial_weights(alphabet_size, prior_weights), precision_bits
        )
        delta = model.get("delta", [])
        if delta:
            if len(delta) != len(baseline):
                raise ValueError("static-adaptive delta must match baseline length")
            frequencies = [base + int(offset) for base, offset in zip(baseline, delta)]
        else:
            frequencies = baseline
        if any(freq <= 0 for freq in frequencies):
            raise ValueError("static-adaptive frequencies must be positive")
        if sum(frequencies) != (1 << precision_bits):
            raise ValueError("static-adaptive frequencies must sum to the model table size")
        model = {"precision_bits": precision_bits, "frequencies": frequencies}
    else:
        precision_bits = int(model.get("precision_bits", 12))
        frequencies = model.get("frequencies")
        if not isinstance(frequencies, list):
            raise ValueError("model frequencies must be a list")
    data_b64 = channel.get("data", "")
    if not isinstance(data_b64, str):
        raise ValueError("channel data must be base64 text")
    compressed = base64.b64decode(data_b64.encode("ascii"))
    backend = RANSBackend(precision_bits=precision_bits)
    return backend.decode(compressed, model, symbol_count)


def _empty_channel(
    *,
    precision_bits: int = 12,
    model_type: str = "adaptive",
    alphabet_size: int = 0,
    prior_model: Optional[Dict[str, Any]] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    if alphabet_size > (1 << precision_bits):
        precision_bits = max(precision_bits, (alphabet_size - 1).bit_length())
    model: Dict[str, Any] = {
        "precision_bits": precision_bits,
        "frequencies": [],
        "model_type": model_type,
    }
    if mode:
        model["mode"] = mode
    if prior_model:
        model["prior_model"] = prior_model
    return {
        "symbol_count": 0,
        "alphabet_size": alphabet_size,
        "data": "",
        "model": model,
    }


def _normalise_weights(weights: Sequence[float], precision_bits: int) -> List[int]:
    target = 1 << precision_bits
    total = float(sum(weights))
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    scaled = [max(1, int(weight / total * target)) for weight in weights]
    diff = target - sum(scaled)
    if diff != 0:
        order = sorted(range(len(weights)), key=lambda idx: weights[idx], reverse=diff > 0)
        index = 0
        while diff != 0 and order:
            position = order[index % len(order)]
            if diff > 0:
                scaled[position] += 1
                diff -= 1
            else:
                if scaled[position] > 1:
                    scaled[position] -= 1
                    diff += 1
            index += 1
    if sum(scaled) != target:
        raise ValueError("frequency normalisation failed to reach target total")
    return scaled


def _initial_weights(alphabet_size: int, prior: Optional[Sequence[float]]) -> List[float]:
    if alphabet_size <= 0:
        raise ValueError("alphabet size must be positive")
    if prior is None:
        return [1.0 for _ in range(alphabet_size)]
    weights = list(prior[:alphabet_size])
    if len(weights) < alphabet_size:
        tail_value = weights[-1] if weights else 1.0
        weights.extend([tail_value for _ in range(alphabet_size - len(weights))])
    return [max(weight, 1e-6) for weight in weights]


def _zipf_prior(alphabet_size: int, exponent: float = 1.0) -> List[float]:
    return [1.0 / float(index + 1) ** exponent for index in range(alphabet_size)]


def _geometric_prior(alphabet_size: int, alpha: float = 0.5) -> List[float]:
    base = 1.0 - alpha
    return [base * (alpha ** index) for index in range(alphabet_size)]


def _resolve_prior_weights(
    alphabet_size: int, prior_model: Optional[Dict[str, Any]]
) -> List[float]:
    if prior_model is None:
        return _initial_weights(alphabet_size, None)
    if not isinstance(prior_model, dict):
        raise ValueError("prior_model must be a mapping when provided")
    kind = prior_model.get("type")
    if kind == "zipf":
        exponent = float(prior_model.get("exponent", 1.0))
        return _zipf_prior(alphabet_size, exponent)
    if kind == "geometric":
        alpha = float(prior_model.get("alpha", 0.5))
        return _geometric_prior(alphabet_size, alpha)
    if kind == "bernoulli":
        weights = list(prior_model.get("weights", []))
        if not weights:
            raise ValueError("bernoulli priors require explicit weights")
        tail_value = weights[-1]
        weights = weights[:alphabet_size]
        if len(weights) < alphabet_size:
            weights.extend([tail_value for _ in range(alphabet_size - len(weights))])
        return [max(weight, 1e-6) for weight in weights]
    raise ValueError(f"unknown prior_model type {kind!r}")


def _pack_residuals(residuals: List[int], buckets: List[int]) -> tuple[str, int]:
    bit_length = 0
    accumulator = 0
    for residual, bucket in zip(residuals, buckets):
        if bucket < 0:
            continue
        accumulator = (accumulator << bucket) | residual
        bit_length += bucket
    if bit_length == 0:
        return "", 0
    byte_length = (bit_length + 7) // 8
    data = accumulator.to_bytes(byte_length, "big")
    return base64.b64encode(data).decode("ascii"), bit_length


def _unpack_residuals(data_b64: str, bit_length: int, buckets: List[int]) -> List[int]:
    if bit_length == 0 or not buckets:
        return []
    raw = base64.b64decode(data_b64.encode("ascii")) if data_b64 else b""
    accumulator = int.from_bytes(raw, "big") if raw else 0
    excess_bits = len(raw) * 8 - bit_length
    if excess_bits > 0:
        accumulator &= (1 << bit_length) - 1
    residuals_reversed: List[int] = []
    for bucket in reversed(buckets):
        if bucket == 0:
            residuals_reversed.append(0)
            continue
        mask = (1 << bucket) - 1
        residuals_reversed.append(accumulator & mask)
        accumulator >>= bucket
    residuals_reversed.reverse()
    return residuals_reversed

