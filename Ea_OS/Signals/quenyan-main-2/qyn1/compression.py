"""Compression backend management for morpheme streams."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Protocol

from .models import (
    GlobalModelRegistry,
    ModelMode,
    apply_hybrid_overrides,
    resolve_model_mode,
)


# ---------------------------------------------------------------------------
# rANS implementation retained from the previous revision


@dataclass
class RANSTable:
    """Pre-computed tables for table-based rANS."""

    precision_bits: int
    frequencies: List[int]
    cumulative: List[int]
    lookup: List[int]

    @property
    def total(self) -> int:
        return 1 << self.precision_bits

    @property
    def mask(self) -> int:
        return self.total - 1

    @property
    def normalization(self) -> int:
        return 1 << 24


class ANSCompressionError(RuntimeError):
    """Raised when decoding encounters malformed data."""


class RANSCodec:
    """Simple table-based rANS compressor/decompressor."""

    def __init__(self, precision_bits: int = 12) -> None:
        if precision_bits < 8 or precision_bits > 16:
            raise ValueError("precision_bits must be between 8 and 16")
        self.precision_bits = precision_bits

    def build_table(self, symbols: Iterable[int], alphabet_size: int) -> RANSTable:
        counts = [1] * alphabet_size
        for symbol in symbols:
            counts[symbol] += 1
        scaled = self._scale_counts(counts)
        cumulative = []
        total = 0
        lookup = [0] * (1 << self.precision_bits)
        for index, freq in enumerate(scaled):
            cumulative.append(total)
            for offset in range(freq):
                lookup[total + offset] = index
            total += freq
        return RANSTable(self.precision_bits, scaled, cumulative, lookup)

    def table_from_model(self, model: Dict[str, Any]) -> RANSTable:
        raw_mode = model.get("mode") if isinstance(model, dict) else None
        try:
            mode = resolve_model_mode(raw_mode)
        except ValueError:
            mode = ModelMode.ADAPTIVE
        precision_bits = int(model.get("precision_bits", self.precision_bits))
        if mode is ModelMode.STATIC:
            global_model = GlobalModelRegistry.load(model.get("model_id", "global_v1"))
            frequencies = list(global_model.frequencies)
        elif mode is ModelMode.HYBRID:
            global_model = GlobalModelRegistry.load(model.get("model_id", "global_v1"))
            overrides = {int(k): int(v) for k, v in model.get("overrides", {}).items()}
            frequencies = apply_hybrid_overrides(
                global_model,
                overrides,
                alphabet_size=int(model.get("alphabet_size", global_model.alphabet_size)),
            )
        else:
            frequencies = list(model["frequencies"])
        target_total = 1 << precision_bits
        total_freq = sum(frequencies)
        if total_freq != target_total:
            normalized = [max(1, freq * target_total // max(total_freq, 1)) for freq in frequencies]
            diff = target_total - sum(normalized)
            if diff > 0:
                for idx in range(min(diff, len(normalized))):
                    normalized[idx] += 1
            elif diff < 0:
                for idx in range(len(normalized)):
                    if diff == 0:
                        break
                    if normalized[idx] > 1:
                        normalized[idx] -= 1
                        diff += 1
            frequencies = normalized
        cumulative = []
        total = 0
        lookup = [0] * (1 << precision_bits)
        for index, freq in enumerate(frequencies):
            cumulative.append(total)
            for offset in range(freq):
                lookup[total + offset] = index
            total += freq
        return RANSTable(precision_bits, frequencies, cumulative, lookup)

    def encode(self, symbols: List[int], table: RANSTable) -> bytes:
        state = 1 << 31
        output = bytearray()
        precision_bits = table.precision_bits
        for symbol in reversed(symbols):
            freq = table.frequencies[symbol]
            cum = table.cumulative[symbol]
            while state >= freq << (32 - precision_bits):
                output.append(state & 0xFF)
                state >>= 8
            state = ((state // freq) << precision_bits) + (state % freq) + cum
        output.extend(state.to_bytes(4, "little"))
        return bytes(output)

    def decode(self, data: bytes, table: RANSTable, symbol_count: int) -> List[int]:
        if len(data) < 4:
            raise ANSCompressionError("encoded stream too short")
        state = int.from_bytes(data[-4:], "little")
        buffer = data[:-4]
        index = len(buffer) - 1
        symbols: List[int] = []
        mask = table.mask
        precision_bits = table.precision_bits
        normalization = table.normalization
        for _ in range(symbol_count):
            x = state & mask
            symbol = table.lookup[x]
            symbols.append(symbol)
            freq = table.frequencies[symbol]
            cum = table.cumulative[symbol]
            state = freq * (state >> precision_bits) + (x - cum)
            while state < normalization:
                if index < 0:
                    raise ANSCompressionError("ran out of renormalisation bytes")
                state = (state << 8) | buffer[index]
                index -= 1
        return symbols

    # ------------------------------------------------------------------

    def _scale_counts(self, counts: List[int]) -> List[int]:
        total = sum(counts)
        target = 1 << self.precision_bits
        scaled = [max(1, count * target // total) for count in counts]
        diff = target - sum(scaled)
        if diff > 0:
            for index in self._sorted_indices(counts):
                if diff == 0:
                    break
                scaled[index] += 1
                diff -= 1
        elif diff < 0:
            for index in self._sorted_indices(counts, reverse=True):
                if diff == 0:
                    break
                if scaled[index] > 1:
                    scaled[index] -= 1
                    diff += 1
        if sum(scaled) != target:
            raise ANSCompressionError("frequency normalisation failed")
        return scaled

    @staticmethod
    def _sorted_indices(counts: List[int], reverse: bool = False) -> List[int]:
        return sorted(range(len(counts)), key=lambda i: counts[i], reverse=reverse)


# ---------------------------------------------------------------------------
# Backend management


class CompressionBackend(Protocol):
    """Interface implemented by compression backends."""

    name: str

    def build_model(self, symbols: Iterable[int], alphabet_size: int) -> Dict[str, Any]:
        ...

    def encode(self, symbols: List[int], model: Dict[str, Any]) -> bytes:
        ...

    def decode(self, data: bytes, model: Dict[str, Any], symbol_count: int) -> List[int]:
        ...


class RANSBackend:
    """Built-in backend using the pure Python rANS codec."""

    name = "rans"

    def __init__(self, precision_bits: int = 12) -> None:
        self._precision_bits = precision_bits
        self._codec = RANSCodec(precision_bits)

    def build_model(self, symbols: Iterable[int], alphabet_size: int) -> Dict[str, Any]:
        table = self._codec.build_table(symbols, alphabet_size)
        return {
            "precision_bits": table.precision_bits,
            "frequencies": table.frequencies,
        }

    def encode(self, symbols: List[int], model: Dict[str, Any]) -> bytes:
        table = self._codec.table_from_model(model)
        return self._codec.encode(symbols, table)

    def decode(self, data: bytes, model: Dict[str, Any], symbol_count: int) -> List[int]:
        table = self._codec.table_from_model(model)
        return self._codec.decode(data, table, symbol_count)


class ChunkedRANSBackend:
    """Chunked rANS backend optimised for streaming token buffers."""

    name = "chunked-rans"

    def __init__(self, *, chunk_size: int = 65536, precision_bits: int = 12) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._chunk_size = chunk_size
        self._precision_bits = precision_bits
        self._codec = RANSCodec(precision_bits)

    def build_model(self, symbols: Iterable[int], alphabet_size: int) -> Dict[str, Any]:
        return {
            "mode": "chunked",
            "chunk_size": self._chunk_size,
            "precision_bits": self._precision_bits,
            "alphabet_size": alphabet_size,
            "chunks": [],
        }

    def _chunk_iter(self, symbols: Iterable[int]) -> Iterator[List[int]]:
        if hasattr(symbols, "iter_chunks"):
            for chunk in symbols.iter_chunks(self._chunk_size):
                chunk_list = list(chunk)
                if chunk_list:
                    yield chunk_list
            return
        buffer: List[int] = []
        for symbol in symbols:
            buffer.append(symbol)
            if len(buffer) >= self._chunk_size:
                yield buffer
                buffer = []
        if buffer:
            yield buffer

    def encode(self, symbols: Iterable[int], model: Dict[str, Any]) -> bytes:
        alphabet_size = int(model["alphabet_size"])
        precision_bits = int(model.get("precision_bits", self._precision_bits))
        codec = RANSCodec(precision_bits)
        compressed = bytearray()
        chunks_meta: List[Dict[str, Any]] = []
        offset = 0
        for chunk in self._chunk_iter(symbols):
            table = codec.build_table(chunk, alphabet_size)
            encoded = codec.encode(chunk, table)
            entry = {
                "offset": offset,
                "length": len(encoded),
                "symbol_count": len(chunk),
                "frequencies": table.frequencies,
            }
            chunks_meta.append(entry)
            compressed.extend(encoded)
            offset += len(encoded)
        model["chunks"] = chunks_meta
        return bytes(compressed)

    def decode(self, data: bytes, model: Dict[str, Any], symbol_count: int) -> List[int]:
        precision_bits = int(model.get("precision_bits", self._precision_bits))
        codec = RANSCodec(precision_bits)
        chunks = model.get("chunks")
        if not isinstance(chunks, list):
            raise ANSCompressionError("chunk metadata missing for chunked-rans backend")
        decoded: List[int] = []
        for entry in chunks:
            offset = int(entry["offset"])
            length = int(entry["length"])
            frequencies = list(entry["frequencies"])
            table = codec.table_from_model(
                {"precision_bits": precision_bits, "frequencies": frequencies}
            )
            segment = data[offset : offset + length]
            chunk_symbols = codec.decode(segment, table, int(entry["symbol_count"]))
            decoded.extend(chunk_symbols)
        if len(decoded) != symbol_count:
            raise ANSCompressionError("decoded symbol count mismatch")
        return decoded


class OptionalBackendUnavailable(RuntimeError):
    """Raised when an optional backend cannot be loaded."""


_SHARED_ENTROPY_DICTIONARIES: Dict[str, Dict[str, Any]] = {}


class FiniteStateEntropyBackend:
    """Production-grade entropy backend with optional python-fse acceleration."""

    name = "fse-production"

    def __init__(
        self,
        *,
        table_log: int = 12,
        dictionary_key: Optional[str] = None,
        enable_simd: bool = True,
        chunk_size: int = 65536,
    ) -> None:
        self._table_log = table_log
        self._dictionary_key = dictionary_key
        self._chunk_size = chunk_size
        self._enable_simd = enable_simd
        self._pyfse = None
        spec = importlib.util.find_spec("pyfse")
        if spec is not None:
            self._pyfse = importlib.import_module("pyfse")

    def _store_dictionary(self, counts: List[int]) -> None:
        if not self._dictionary_key:
            return
        _SHARED_ENTROPY_DICTIONARIES[self._dictionary_key] = {
            "counts": list(counts),
            "table_log": self._table_log,
        }

    # ------------------------------------------------------------------
    # CompressionBackend API

    def build_model(self, symbols: Iterable[int], alphabet_size: int) -> Dict[str, Any]:
        counts = [0] * alphabet_size
        for symbol in symbols:
            counts[symbol] += 1
        self._store_dictionary(counts)
        model: Dict[str, Any] = {
            "table_log": self._table_log,
            "counts": counts,
        }
        if self._dictionary_key:
            model["dictionary_key"] = self._dictionary_key
        if self._pyfse is not None and self._enable_simd:
            try:
                precomputed = self._pyfse.build_ctable(counts, table_log=self._table_log)
            except AttributeError:
                precomputed = None
            if precomputed is not None:
                model["precomputed"] = precomputed
        return model

    def encode(self, symbols: List[int], model: Dict[str, Any]) -> bytes:
        if self._pyfse is not None:
            table_log = int(model.get("table_log", self._table_log))
            counts = model.get("counts")
            precomputed = model.get("precomputed")
            kwargs: Dict[str, Any] = {"table_log": table_log}
            if counts is not None:
                kwargs["counts"] = counts
            if precomputed is not None:
                kwargs["precomputed"] = precomputed
            try:
                return self._pyfse.compress(symbols, **kwargs)
            except TypeError:
                # Older versions of python-fse do not accept keyword arguments
                return self._pyfse.compress(symbols, table_log)
        # Fallback to deterministic rANS implementation
        precision = max(8, min(16, int(model.get("table_log", self._table_log))))
        codec = RANSCodec(precision)
        frequencies = model.get("counts")
        if frequencies is None:
            dictionary_key = model.get("dictionary_key")
            if dictionary_key and dictionary_key in _SHARED_ENTROPY_DICTIONARIES:
                frequencies = _SHARED_ENTROPY_DICTIONARIES[dictionary_key]["counts"]
        if frequencies is None:
            raise ANSCompressionError("compression model missing frequency table")
        table = codec.table_from_model(
            {"precision_bits": precision, "frequencies": list(frequencies)}
        )
        return codec.encode(symbols, table)

    def decode(self, data: bytes, model: Dict[str, Any], symbol_count: int) -> List[int]:
        if self._pyfse is not None:
            counts = model.get("counts")
            kwargs: Dict[str, Any] = {}
            if counts is not None:
                kwargs["counts"] = counts
            dictionary_key = model.get("dictionary_key")
            if dictionary_key and dictionary_key in _SHARED_ENTROPY_DICTIONARIES:
                kwargs.setdefault("counts", _SHARED_ENTROPY_DICTIONARIES[dictionary_key]["counts"])
            return list(self._pyfse.decompress(data, symbol_count, **kwargs))
        precision = max(8, min(16, int(model.get("table_log", self._table_log))))
        codec = RANSCodec(precision)
        frequencies = model.get("counts")
        if frequencies is None:
            dictionary_key = model.get("dictionary_key")
            if dictionary_key and dictionary_key in _SHARED_ENTROPY_DICTIONARIES:
                frequencies = _SHARED_ENTROPY_DICTIONARIES[dictionary_key]["counts"]
        if frequencies is None:
            raise ANSCompressionError("compression model missing frequency table")
        table = codec.table_from_model(
            {"precision_bits": precision, "frequencies": list(frequencies)}
        )
        return codec.decode(data, table, symbol_count)

    # ------------------------------------------------------------------
    # Extended API

    def decode_iter(
        self,
        data: bytes,
        model: Dict[str, Any],
        symbol_count: int,
        *,
        chunk_size: Optional[int] = None,
    ) -> Iterator[List[int]]:
        chunk = chunk_size or self._chunk_size
        decoded = self.decode(data, model, symbol_count)
        for offset in range(0, len(decoded), chunk):
            yield decoded[offset : offset + chunk]


class FSEBackend(FiniteStateEntropyBackend):
    """Backwards compatible alias for the legacy backend name."""

    name = "fse"


class DudaBackend:
    """Wrapper for Jarek Duda's reference rANS implementation via constriction."""

    name = "duda"

    def __init__(self) -> None:
        module = importlib.util.find_spec("constriction")
        if module is None:
            raise OptionalBackendUnavailable("constriction (Duda reference bindings) is not installed")
        self._constriction = importlib.import_module("constriction")

    def build_model(self, symbols: Iterable[int], alphabet_size: int) -> Dict[str, Any]:
        counts = [0] * alphabet_size
        for symbol in symbols:
            counts[symbol] += 1
        return {"counts": counts}

    def encode(self, symbols: List[int], model: Dict[str, Any]) -> bytes:
        encoder = self._constriction.stream.queue.BitQueueEncoder()
        table = self._constriction.stream.model.CategoricalEntropyModel(model["counts"])
        encoder.encode_reverse(table, symbols)
        return bytes(encoder.get_compressed())

    def decode(self, data: bytes, model: Dict[str, Any], symbol_count: int) -> List[int]:
        decoder = self._constriction.stream.queue.BitQueueDecoder(bytearray(data))
        table = self._constriction.stream.model.CategoricalEntropyModel(model["counts"])
        result = list(decoder.decode_reverse(table, symbol_count))
        result.reverse()
        return result


_BACKEND_FACTORIES = {
    "rans": RANSBackend,
    "chunked-rans": ChunkedRANSBackend,
    "fse": FSEBackend,
    "fse-production": FiniteStateEntropyBackend,
    "duda": DudaBackend,
}


def get_backend(name: str, **options: Any) -> CompressionBackend:
    try:
        factory = _BACKEND_FACTORIES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown compression backend: {name}") from exc
    if options:
        signature = inspect.signature(factory)
        try:
            signature.bind_partial(**options)
        except TypeError as exc:
            raise ValueError(
                f"Compression backend '{name}' does not accept options: {sorted(options.keys())}"
            ) from exc
        backend = factory(**options)
    else:
        backend = factory()
    return backend


def available_backends() -> Dict[str, str]:
    """Return mapping of backend name to availability status message."""

    availability: Dict[str, str] = {}
    for name, factory in _BACKEND_FACTORIES.items():
        try:
            factory()
        except OptionalBackendUnavailable as exc:
            availability[name] = str(exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            availability[name] = f"error: {exc}"  # type: ignore[unreachable]
        else:
            availability[name] = "available"
    return availability


def decompress_bytes(
    backend_name: str,
    model: Dict[str, Any],
    payload: bytes,
    symbol_count: int,
) -> List[int]:
    """Decode ``payload`` produced by the specified backend.

    The helper is a thin wrapper around :func:`get_backend` that centralises
    error handling so that external fuzzing harnesses and regression tests can
    exercise the decompression path without re-implementing backend lookup
    logic.  The return value is the decoded symbol stream.
    """

    backend = get_backend(backend_name)
    return backend.decode(payload, model, symbol_count)


__all__ = [
    "ANSCompressionError",
    "CompressionBackend",
    "RANSBackend",
    "ChunkedRANSBackend",
    "DudaBackend",
    "OptionalBackendUnavailable",
    "get_backend",
    "available_backends",
    "RANSTable",
    "RANSCodec",
]
