"""AST to morpheme stream encoder with dictionary versioning."""

from __future__ import annotations

import ast
import hashlib
import platform
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Protocol, Sequence, Union
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - optional import for type checkers
    from .io import ChunkedSource

from .dictionary import MorphemeDictionary, ensure_dictionary_supported, load_dictionary
from .event_logging import EncodingEventLog, EventPayloadClass
from .language_profiles import (
    LanguageProfile,
    LanguageProfileRegistry,
    default_registry,
    profile_for_path,
    resolve_profile_spec,
)
from .payloads import Payload, PayloadChannels
from .source_map import SourceMap, SourceMapBuilder

ENCODER_VERSION = "1.0"


class TokenBuffer(Protocol):
    """Lightweight protocol for token collectors used by the encoder."""

    def append(self, value: int) -> None:
        ...

    def __len__(self) -> int:
        ...

    def __iter__(self) -> Iterator[int]:
        ...


class HumanBuffer(Protocol):
    """Protocol capturing the minimal interface needed for human tokens."""

    def append(self, value: str) -> None:
        ...

    def __len__(self) -> int:
        ...

    def __iter__(self) -> Iterator[str]:
        ...


@dataclass
class EncodedStream:
    """Encoded representation of a Python module."""

    dictionary: MorphemeDictionary
    tokens: Sequence[int]
    payloads: List[Payload]
    payload_channels: PayloadChannels
    encoder_version: str
    human_readable: Sequence[str]
    source_language: str = "unknown"
    source_language_version: str = "unknown"
    source_hash: str = ""
    source_encoding: str = "utf-8"
    license: Optional[str] = None
    author: Optional[str] = None
    timestamp: Optional[str] = None
    source_map: Optional[SourceMap] = None

    @property
    def dictionary_version(self) -> str:
        return self.dictionary.version

    def describe(self) -> str:
        """Return a human readable morpheme sequence."""

        if not self.human_readable:
            return ""
        return " ".join(self.human_readable)


@dataclass
class QYNEncoder:
    """Encode source code into a canonical morphemic stream."""

    dictionary_version: str = "1.0"
    dictionary: Optional[MorphemeDictionary] = None
    strict_morpheme_errors: bool = False
    language_profile_name: str = "python"
    language_profile: Optional[LanguageProfile] = None
    language_profile_registry: LanguageProfileRegistry = default_registry()
    _BOOLEAN_PAYLOAD_TYPES = {"function_async", "return_has_value"}
    _source_map_builder: SourceMapBuilder | None = None
    _current_node: Optional[ast.AST] = None
    _token_cache: Dict[str, tuple[int, str, str]] = field(init=False, default_factory=dict)
    _source_encoding: str = "utf-8"
    _event_log: EncodingEventLog | None = None

    def __post_init__(self) -> None:
        if self.dictionary is None:
            self.dictionary = load_dictionary(
                self.dictionary_version, strict_morpheme_errors=self.strict_morpheme_errors
            )
        else:
            self.dictionary_version = self.dictionary.version
            if self.strict_morpheme_errors and not self.dictionary.strict_morpheme_errors:
                self.dictionary.strict_morpheme_errors = True
        self.strict_morpheme_errors = self.dictionary.strict_morpheme_errors
        if self.language_profile is None:
            self.language_profile = self.language_profile_registry.resolve(self.language_profile_name)
        else:
            self.language_profile_name = self.language_profile.name
        self._token_cache.clear()
        ensure_dictionary_supported(self.dictionary.version)

    # ------------------------------------------------------------------
    # Public API

    def encode(
        self,
        source: Union[str, bytes, bytearray, memoryview, "ChunkedSource"],
        *,
        token_buffer: Optional[TokenBuffer] = None,
        human_buffer: Optional[HumanBuffer] = None,
        language_profile: Optional[Union[LanguageProfile, str, Path]] = None,
        source_path: Optional[Union[str, Path]] = None,
        mime_type: Optional[str] = None,
        source_encoding: Optional[str] = None,
        event_log: Optional[EncodingEventLog] = None,
    ) -> EncodedStream:
        """Encode *source* into an :class:`EncodedStream`.

        Callers may supply an explicit ``language_profile`` name, alias, manifest
        path, or profile instance. When omitted, the encoder will attempt to
        resolve a profile from ``source_path`` (using file extensions and MIME
        hints) before falling back to the configured default.
        """
        module = self._parse_source(source)
        previous_profile: Optional[LanguageProfile] = None
        resolved_profile: Optional[LanguageProfile] = None
        if language_profile is not None:
            resolved_profile = resolve_profile_spec(
                str(language_profile) if isinstance(language_profile, Path) else language_profile,
                registry=self.language_profile_registry,
                fallback=self.language_profile_name,
            )
        elif source_path is not None:
            resolved_profile = profile_for_path(
                source_path,
                registry=self.language_profile_registry,
                mime_type=mime_type,
                fallback=self.language_profile_name,
            )
        if resolved_profile is not None:
            previous_profile = self.language_profile
            self.language_profile = resolved_profile
            self.language_profile_name = resolved_profile.name
        if self.language_profile is None:
            raise ValueError("language profile is not configured")
        previous_encoding: Optional[str] = None
        if source_encoding is not None:
            previous_encoding = self._source_encoding
            self._source_encoding = source_encoding
        self._event_log = event_log
        tokens: TokenBuffer
        if token_buffer is None:
            tokens = []  # type: ignore[assignment]
        else:
            tokens = token_buffer
        payload_channels = PayloadChannels()
        if human_buffer is None:
            human: HumanBuffer = []  # type: ignore[assignment]
        else:
            human = human_buffer
        self._source_map_builder = SourceMapBuilder()
        self._current_node = None

        self._emit_token("meta:stream_start", tokens, human)
        self._emit_token("meta:version_header", tokens, human)
        payload_channels.append_string(
            "encoder_version", ENCODER_VERSION, token_index=len(tokens) - 1
        )
        self._emit_token("meta:dictionary_version", tokens, human)
        payload_channels.append_string(
            "dictionary_version", self.dictionary.version, token_index=len(tokens) - 1
        )

        self._emit_module(module, tokens, payload_channels, human)

        self._emit_token("meta:stream_end", tokens, human)

        source_hash = self._hash_source(source)

        source_map = None
        if self._source_map_builder is not None:
            source_map = self._source_map_builder.build(
                source_hash,
                self.dictionary.version,
                ENCODER_VERSION,
            )

        payloads = payload_channels.to_payloads()
        stream = EncodedStream(
            dictionary=self.dictionary,
            tokens=tokens,
            payloads=payloads,
            payload_channels=payload_channels,
            encoder_version=ENCODER_VERSION,
            human_readable=human,
            source_language=self.language_profile.name if self.language_profile else "unknown",
            source_language_version=self.language_profile.version if self.language_profile else platform.python_version(),
            source_hash=source_hash,
            source_encoding=self._source_encoding,
            source_map=source_map,
        )
        if previous_profile is not None:
            self.language_profile = previous_profile
            self.language_profile_name = previous_profile.name
        if previous_encoding is not None:
            self._source_encoding = previous_encoding
        self._event_log = None
        return stream

    def _parse_source(self, source: Union[str, bytes, bytearray, memoryview, "ChunkedSource"]) -> ast.AST:
        if hasattr(source, "ast") and callable(getattr(source, "ast")):
            module = source.ast()  # type: ignore[assignment]
        else:
            module = ast.parse(source)  # type: ignore[arg-type]
        ast.fix_missing_locations(module)
        return module

    def _hash_source(self, source: Union[str, bytes, bytearray, memoryview, "ChunkedSource"]) -> str:
        hasher = hashlib.sha256()
        if hasattr(source, "iter_bytes") and callable(getattr(source, "iter_bytes")):
            for chunk in source.iter_bytes():  # type: ignore[attr-defined]
                hasher.update(chunk)
        elif isinstance(source, str):
            hasher.update(source.encode("utf-8"))
        elif isinstance(source, (bytes, bytearray)):
            hasher.update(source)
        else:
            hasher.update(memoryview(source))
        return hasher.hexdigest()

    # ------------------------------------------------------------------
    # Emitters

    def _emit_token(
        self,
        key: str,
        tokens: List[int],
        human: List[str],
        node: Optional[ast.AST] = None,
    ) -> int:
        cached = self._token_cache.get(key)
        if cached is None:
            index = self.dictionary.index_for_key(key)
            entry = self.dictionary.entry_for_index(index)
            cached = (index, f"{entry.morpheme}<{entry.key}>", entry.key)
            self._token_cache[key] = cached
        index, human_text, entry_key = cached
        human.append(human_text)
        tokens.append(index)
        if self._source_map_builder is not None:
            resolved = node or self._current_node
            self._source_map_builder.record(len(tokens) - 1, entry_key, resolved)
        if self._event_log is not None:
            self._event_log.record_token(entry_key)
        return index

    @contextmanager
    def _node_context(self, node: Optional[ast.AST]):
        previous = self._current_node
        if node is not None:
            self._current_node = node
        try:
            yield
        finally:
            self._current_node = previous

    def _emit_module(
        self,
        module: ast.Module,
        tokens: List[int],
        payloads: PayloadChannels,
        human: List[str],
    ) -> None:
        with self._node_context(module):
            self._emit_token("construct:module", tokens, human)
            payloads.append_count(
                "module_body_length", len(module.body), token_index=len(tokens) - 1
            )
            self._record_payload_event(
                len(tokens) - 1,
                "module_body_length",
                "C",
                len(module.body),
            )
            for stmt in module.body:
                self._emit_statement(stmt, tokens, payloads, human)

    def _emit_statement(
        self,
        node: ast.AST,
        tokens: List[int],
        payloads: PayloadChannels,
        human: List[str],
    ) -> None:
        with self._node_context(node):
            if isinstance(node, ast.ImportFrom):
                self._emit_token("construct:import", tokens, human)
                payloads.append_structured(
                    "import_spec",
                    {
                        "module": node.module,
                        "level": node.level or 0,
                        "names": [(alias.name, alias.asname) for alias in node.names],
                    },
                    token_index=len(tokens) - 1,
                )
                self._record_payload_event(
                    len(tokens) - 1,
                    "import_spec",
                    "R",
                    {
                        "module": node.module,
                        "level": node.level or 0,
                        "names": [(alias.name, alias.asname) for alias in node.names],
                    },
                )
                return
            if isinstance(node, ast.FunctionDef):
                self._emit_function(node, False, tokens, payloads, human)
                return
            if isinstance(node, ast.AsyncFunctionDef):
                self._emit_function(node, True, tokens, payloads, human)
                return
            if isinstance(node, ast.Assign):
                self._emit_token("op:assign", tokens, human)
                payloads.append_count(
                    "assign_target_count", len(node.targets), token_index=len(tokens) - 1
                )
                self._record_payload_event(
                    len(tokens) - 1,
                    "assign_target_count",
                    "C",
                    len(node.targets),
                )
                for target in node.targets:
                    self._emit_expression(target, tokens, payloads, human)
                self._emit_expression(node.value, tokens, payloads, human)
                return
            if isinstance(node, ast.Return):
                self._emit_token("flow:return", tokens, human)
                has_value = node.value is not None
                payloads.append_count(
                    "return_has_value", int(has_value), token_index=len(tokens) - 1
                )
                self._record_payload_event(
                    len(tokens) - 1,
                    "return_has_value",
                    "C",
                    int(has_value),
                )
                if has_value:
                    self._emit_expression(node.value, tokens, payloads, human)
                return
            if isinstance(node, ast.Expr):
                # expression statements reuse expression encoder
                self._emit_expression(node.value, tokens, payloads, human)
                return
            # Fallback
            self._emit_token("meta:unknown", tokens, human)
            payloads.append_structured(
                "unknown_statement", ast.dump(node), token_index=len(tokens) - 1
            )
            self._record_payload_event(
                len(tokens) - 1,
                "unknown_statement",
                "R",
                ast.dump(node),
            )

    def _emit_function(
        self,
        node: ast.FunctionDef,
        is_async: bool,
        tokens: List[int],
        payloads: PayloadChannels,
        human: List[str],
    ) -> None:
        with self._node_context(node):
            self._emit_token("construct:function", tokens, human)
            payloads.append_identifier(
                "function_name", node.name, token_index=len(tokens) - 1
            )
            self._record_payload_event(
                len(tokens) - 1, "function_name", "I", node.name
            )
            payloads.append_count(
                "function_async", int(is_async), token_index=len(tokens) - 1
            )
            self._record_payload_event(
                len(tokens) - 1, "function_async", "C", int(is_async)
            )
            return_spec = self._extract_type_spec(node.returns)
            payloads.append_structured(
                "function_return", return_spec, token_index=len(tokens) - 1
            )
            self._record_payload_event(
                len(tokens) - 1, "function_return", "R", return_spec
            )
            args = node.args
            params: List[Dict[str, Any]] = []
            for arg in args.posonlyargs + args.args:
                params.append(
                    {
                        "name": arg.arg,
                        "type_spec": self._extract_type_spec(arg.annotation),
                    }
                )
            payloads.append_count(
                "function_arg_count", len(params), token_index=len(tokens) - 1
            )
            self._record_payload_event(
                len(tokens) - 1, "function_arg_count", "C", len(params)
            )
            for spec in params:
                self._emit_token("structure:parameter", tokens, human)
                payloads.append_identifier(
                    "parameter_name", spec["name"], token_index=len(tokens) - 1
                )
                self._record_payload_event(
                    len(tokens) - 1, "parameter_name", "I", spec["name"]
                )
                payloads.append_structured(
                    "parameter_type", spec.get("type_spec"), token_index=len(tokens) - 1
                )
                self._record_payload_event(
                    len(tokens) - 1,
                    "parameter_type",
                    "R",
                    spec.get("type_spec"),
                )
            payloads.append_count(
                "function_body_length", len(node.body), token_index=len(tokens) - 1
            )
            self._record_payload_event(
                len(tokens) - 1, "function_body_length", "C", len(node.body)
            )
            for stmt in node.body:
                self._emit_statement(stmt, tokens, payloads, human)

    def _emit_expression(
        self,
        node: ast.AST,
        tokens: List[int],
        payloads: PayloadChannels,
        human: List[str],
    ) -> None:
        with self._node_context(node):
            if isinstance(node, ast.Name):
                self._emit_token("structure:identifier", tokens, human)
                payloads.append_identifier(
                    "identifier_name", node.id, token_index=len(tokens) - 1
                )
                self._record_payload_event(
                    len(tokens) - 1, "identifier_name", "I", node.id
                )
                payloads.append_count(
                    "identifier_ctx", self._encode_identifier_ctx(node), token_index=len(tokens) - 1
                )
                self._record_payload_event(
                    len(tokens) - 1,
                    "identifier_ctx",
                    "C",
                    self._encode_identifier_ctx(node),
                )
                return
            if isinstance(node, ast.Constant):
                key, literal_value, channel, kind = self._literal_entry(node.value)
                self._emit_token(key, tokens, human)
                if channel == "S":
                    payloads.append_string(
                        "literal", literal_value, kind=kind, token_index=len(tokens) - 1
                    )
                    self._record_payload_event(
                        len(tokens) - 1,
                        "literal",
                        channel,
                        literal_value,
                        kind=kind,
                    )
                elif channel == "N":
                    payloads.append_number(
                        "literal", literal_value, kind=kind, token_index=len(tokens) - 1
                    )
                    self._record_payload_event(
                        len(tokens) - 1,
                        "literal",
                        channel,
                        literal_value,
                        kind=kind,
                    )
                elif channel == "C":
                    payloads.append_count(
                        "literal", literal_value, kind=kind, token_index=len(tokens) - 1
                    )
                    self._record_payload_event(
                        len(tokens) - 1,
                        "literal",
                        channel,
                        literal_value,
                        kind=kind,
                    )
                else:
                    payloads.append_structured(
                        "literal", literal_value, kind=kind, token_index=len(tokens) - 1
                    )
                    self._record_payload_event(
                        len(tokens) - 1,
                        "literal",
                        channel,
                        literal_value,
                        kind=kind,
                    )
                return
            if isinstance(node, ast.BinOp):
                key = self.language_profile.binary_operator_key(type(node.op).__name__)
                self._emit_token(key, tokens, human)
                if key == self.language_profile.literal_profile.fallback:
                    payloads.append_string(
                        "operator_repr",
                        type(node.op).__name__,
                        token_index=len(tokens) - 1,
                    )
                    self._record_payload_event(
                        len(tokens) - 1,
                        "operator_repr",
                        "S",
                        type(node.op).__name__,
                    )
                self._emit_expression(node.left, tokens, payloads, human)
                self._emit_expression(node.right, tokens, payloads, human)
                return
            if isinstance(node, ast.UnaryOp):
                key = self.language_profile.unary_operator_key(type(node.op).__name__)
                self._emit_token(key, tokens, human)
                if key == self.language_profile.literal_profile.fallback:
                    payloads.append_string(
                        "unary_repr", type(node.op).__name__, token_index=len(tokens) - 1
                    )
                    self._record_payload_event(
                        len(tokens) - 1,
                        "unary_repr",
                        "S",
                        type(node.op).__name__,
                    )
                self._emit_expression(node.operand, tokens, payloads, human)
                return
            if isinstance(node, ast.Call):
                self._emit_token("op:call", tokens, human)
                payloads.append_count(
                    "call_arg_count", len(node.args), token_index=len(tokens) - 1
                )
                self._record_payload_event(
                    len(tokens) - 1, "call_arg_count", "C", len(node.args)
                )
                payloads.append_count(
                    "call_keyword_count", len(node.keywords), token_index=len(tokens) - 1
                )
                self._record_payload_event(
                    len(tokens) - 1,
                    "call_keyword_count",
                    "C",
                    len(node.keywords),
                )
                self._emit_expression(node.func, tokens, payloads, human)
                for arg in node.args:
                    self._emit_expression(arg, tokens, payloads, human)
                for keyword in node.keywords:
                    payloads.append_identifier(
                        "call_keyword_name", keyword.arg, token_index=len(tokens) - 1
                    )
                    self._record_payload_event(
                        len(tokens) - 1, "call_keyword_name", "I", keyword.arg
                    )
                    self._emit_expression(keyword.value, tokens, payloads, human)
                return
            if isinstance(node, ast.Attribute):
                self._emit_token("structure:qualifier", tokens, human)
                payloads.append_identifier(
                    "attribute_name", node.attr, token_index=len(tokens) - 1
                )
                self._record_payload_event(
                    len(tokens) - 1, "attribute_name", "I", node.attr
                )
                self._emit_expression(node.value, tokens, payloads, human)
                return
            if isinstance(node, ast.Subscript):
                self._emit_token("structure:spread", tokens, human)
                self._emit_expression(node.value, tokens, payloads, human)
                self._emit_expression(node.slice, tokens, payloads, human)
                return
            self._emit_token("meta:unknown", tokens, human)
            payloads.append_structured(
                "unknown_expression", ast.dump(node), token_index=len(tokens) - 1
            )
            self._record_payload_event(
                len(tokens) - 1,
                "unknown_expression",
                "R",
                ast.dump(node),
            )

    # ------------------------------------------------------------------
    # Helpers

    def _record_payload_event(
        self,
        token_index: int,
        payload_type: str,
        channel: str,
        value: Any,
        *,
        kind: Optional[str] = None,
    ) -> None:
        if self._event_log is None:
            return
        payload_domain = kind or payload_type
        payload_class = EventPayloadClass.OTHER
        payload_value: Any = value
        raw_string: Optional[str] = None
        if channel == "I":
            payload_class = EventPayloadClass.ID
            raw_string = str(value)
            payload_value = None
        elif channel == "S":
            payload_class = EventPayloadClass.STR
            raw_string = str(value)
            payload_value = None
        elif channel == "N":
            payload_class = EventPayloadClass.NUM
        elif channel == "C":
            if payload_type in self._BOOLEAN_PAYLOAD_TYPES or isinstance(value, bool):
                payload_class = EventPayloadClass.BOOL
                payload_value = bool(value)
            else:
                payload_class = EventPayloadClass.NUM
                payload_value = int(value)
        elif channel == "F":
            payload_class = EventPayloadClass.BOOL
            payload_value = bool(value)
        self._event_log.record_payload(
            token_index,
            payload_class,
            payload_value=payload_value,
            payload_domain=payload_domain,
            raw_string=raw_string,
        )

    def _literal_entry(self, value: Any) -> tuple[str, Any, str, Optional[str]]:
        literals = self.language_profile.literal_profile
        if isinstance(value, bool):
            key = literals.bool_true if value else literals.bool_false
            return (key, int(value), "C", key)
        if value is None:
            return (literals.null, 0, "C", literals.null)
        if isinstance(value, str):
            key = literals.wide_string or literals.string
            return (key, value, "S", key)
        if isinstance(value, bytes):
            return (literals.bytes, value.hex(), "S", literals.bytes)
        if isinstance(value, int):
            return (literals.integer, value, "N", literals.integer)
        if isinstance(value, float):
            return (literals.floating, value, "N", literals.floating)
        return (literals.fallback, {"repr": repr(value)}, "R", literals.fallback)

    def _encode_identifier_ctx(self, node: ast.Name) -> int:
        ctx_name = type(node.ctx).__name__
        mapping = {"Load": 0, "Store": 1, "Del": 2}
        return mapping.get(ctx_name, 0)

    def _extract_type_spec(self, annotation: Optional[ast.AST]) -> Optional[Dict[str, Any]]:
        if annotation is None:
            return None
        if isinstance(annotation, ast.Name):
            key = self.language_profile.normalise_type_name(annotation.id)
            return {
                "type_key": key,
                "repr": annotation.id,
                "args": [],
            }
        if isinstance(annotation, ast.Subscript):
            base = self._extract_type_spec(annotation.value)
            if isinstance(annotation.slice, ast.Tuple):
                args = [self._extract_type_spec(elt) for elt in annotation.slice.elts]
            else:
                args = [self._extract_type_spec(annotation.slice)]
            return {
                "type_key": None if base is None else base.get("type_key"),
                "repr": None if base is None else base.get("repr"),
                "args": args,
            }
        if isinstance(annotation, ast.Attribute):
            text = ast.unparse(annotation)
            key = self.language_profile.normalise_type_name(annotation.attr)
            return {
                "type_key": key,
                "repr": text,
                "args": [],
            }
        return {
            "type_key": None,
            "repr": ast.unparse(annotation),
            "args": [],
        }
