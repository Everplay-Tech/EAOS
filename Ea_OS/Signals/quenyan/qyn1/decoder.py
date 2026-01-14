"""Inverse of the morphemic encoder."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .dictionary import MorphemeDictionary, load_dictionary
from .language_profiles import LanguageProfile, load_language_profile
from .payloads import Payload, PayloadChannels


@dataclass
class _ANSChannelState:
    """Track decoding progress through token and payload sub-streams."""

    dictionary: MorphemeDictionary
    tokens: Sequence[int]
    payload_channels: PayloadChannels
    token_index: int = 0

    def __post_init__(self) -> None:
        self._payload_cursor = self.payload_channels.cursor()

    def next_token_key(self) -> str:
        key = self.dictionary.key_for_index(self.tokens[self.token_index])
        self.token_index += 1
        return key

    def peek_token_key(self) -> str:
        return self.dictionary.key_for_index(self.tokens[self.token_index])

    def expect_token(self, expected: str) -> None:
        key = self.next_token_key()
        if key != expected:
            raise ValueError(f"Expected token {expected!r}, found {key!r}")

    def next_payload(self, expected_type: str, channel: str) -> Any:
        return self._payload_cursor.consume(expected_type, channel)

    def consume_with_entry(
        self,
        expected_type: str,
        expected_channel: Optional[str] = None,
        *,
        kind: Optional[str] = None,
    ) -> tuple[Any, Any]:
        return self._payload_cursor.consume_with_entry(
            expected_type, expected_channel, kind=kind
        )


@dataclass
class QYNDecoder:
    """Reconstruct Python ASTs from encoded streams."""

    dictionary: MorphemeDictionary
    tokens: List[int]
    payloads: List[Payload]
    payload_channels: Optional[PayloadChannels] = None
    language_profile_name: str = "python"
    language_profile: Optional[LanguageProfile] = None

    def __post_init__(self) -> None:
        if self.payload_channels is None:
            self.payload_channels = PayloadChannels.from_payloads(self.payloads)
        else:
            # The decoder no longer relies on morphemic payload tokens; it expects
            # channelised ANS sub-streams matching the encoder's specialisation
            # (e.g. Zipf priors for identifiers and log buckets for integers).
            self.payloads = self.payloads or []
        self._state = _ANSChannelState(
            dictionary=self.dictionary,
            tokens=self.tokens,
            payload_channels=self.payload_channels,
        )
        if self.language_profile is None:
            self.language_profile = load_language_profile(self.language_profile_name)
        else:
            self.language_profile_name = self.language_profile.name
        self._binop_key_to_class: Dict[str, type[ast.AST]] = {}
        self._unary_key_to_class: Dict[str, type[ast.AST]] = {}
        for operator_name, key in self.language_profile.binary_operators.items():
            cls = getattr(ast, operator_name, None)
            if cls is not None:
                self._binop_key_to_class[key] = cls
        for operator_name, key in self.language_profile.unary_operators.items():
            cls = getattr(ast, operator_name, None)
            if cls is not None and key != self.language_profile.literal_profile.fallback:
                self._unary_key_to_class[key] = cls

    def decode(self) -> ast.AST:
        self._state.expect_token("meta:stream_start")
        self._state.expect_token("meta:version_header")
        _ = self._state.next_payload("encoder_version", "S")
        self._state.expect_token("meta:dictionary_version")
        dictionary_version = self._state.next_payload("dictionary_version", "S")
        if dictionary_version != self.dictionary.version:
            self.dictionary = load_dictionary(dictionary_version)
            self._state.dictionary = self.dictionary
        module = self._read_module()
        self._state.expect_token("meta:stream_end")
        return ast.fix_missing_locations(module)

    # ------------------------------------------------------------------
    # Helpers

    def _peek_token_key(self) -> str:
        return self._state.peek_token_key()

    def _next_payload(self, expected_type: str, channel: str) -> Any:
        return self._state.next_payload(expected_type, channel)

    # ------------------------------------------------------------------
    # Readers

    def _read_module(self) -> ast.Module:
        self._state.expect_token("construct:module")
        length = self._next_payload("module_body_length", "C")
        body = [self._read_statement() for _ in range(length)]
        return ast.Module(body=body, type_ignores=[])

    def _read_statement(self) -> ast.stmt:
        key = self._peek_token_key()
        if key == "construct:import":
            self._state.expect_token("construct:import")
            spec = self._next_payload("import_spec", "R")
            names = [ast.alias(name=name, asname=alias) for name, alias in spec["names"]]
            return ast.ImportFrom(module=spec["module"], names=names, level=spec["level"])
        if key == "construct:function":
            return self._read_function()
        if key == "op:assign":
            self._state.expect_token("op:assign")
            count = self._next_payload("assign_target_count", "C")
            targets = [self._read_expression() for _ in range(count)]
            value = self._read_expression()
            return ast.Assign(targets=targets, value=value)
        if key == "flow:return":
            self._state.expect_token("flow:return")
            has_value = bool(self._next_payload("return_has_value", "C"))
            value = self._read_expression() if has_value else None
            return ast.Return(value=value)
        if key == "meta:unknown":
            self._state.expect_token("meta:unknown")
            _ = self._next_payload("unknown_statement", "R")
            return ast.Pass()
        expr = self._read_expression()
        return ast.Expr(value=expr)

    def _read_function(self) -> ast.stmt:
        self._state.expect_token("construct:function")
        name = self._next_payload("function_name", "I")
        is_async = bool(self._next_payload("function_async", "C"))
        return_spec = self._next_payload("function_return", "R")
        arg_count = self._next_payload("function_arg_count", "C")
        args: List[ast.arg] = []
        for _ in range(arg_count):
            self._state.expect_token("structure:parameter")
            param_name = self._next_payload("parameter_name", "I")
            type_spec = self._next_payload("parameter_type", "R")
            spec = {"name": param_name, "type_spec": type_spec}
            annotation = self._annotation_from_spec(spec.get("type_spec"))
            args.append(ast.arg(arg=spec["name"], annotation=annotation))
        body_length = self._next_payload("function_body_length", "C")
        body = [self._read_statement() for _ in range(body_length)]
        arguments = ast.arguments(
            posonlyargs=[],
            args=args,
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        )
        returns = self._annotation_from_spec(return_spec)
        if is_async:
            return ast.AsyncFunctionDef(
                name=name,
                args=arguments,
                body=body,
                decorator_list=[],
                returns=returns,
                type_comment=None,
            )
        return ast.FunctionDef(
            name=name,
            args=arguments,
            body=body,
            decorator_list=[],
            returns=returns,
            type_comment=None,
        )

    def _read_expression(self) -> ast.expr:
        key = self._peek_token_key()
        if key == "structure:identifier":
            self._state.expect_token("structure:identifier")
            name = self._next_payload("identifier_name", "I")
            ctx_code = int(self._next_payload("identifier_ctx", "C"))
            ctx_name = {0: "Load", 1: "Store", 2: "Del"}.get(ctx_code, "Load")
            ctx = {"Load": ast.Load(), "Store": ast.Store(), "Del": ast.Del()}.get(
                ctx_name,
                ast.Load(),
            )
            return ast.Name(id=name, ctx=ctx)
        if key.startswith("literal:"):
            return self._read_literal()
        if key in self._binop_key_to_class:
            self._state.expect_token(key)
            left = self._read_expression()
            right = self._read_expression()
            return ast.BinOp(left=left, op=self._binop_key_to_class[key](), right=right)
        if key in self._unary_key_to_class:
            self._state.expect_token(key)
            operand = self._read_expression()
            return ast.UnaryOp(op=self._unary_key_to_class[key](), operand=operand)
        if key == "op:call":
            self._state.expect_token("op:call")
            arg_count = self._next_payload("call_arg_count", "C")
            kw_count = self._next_payload("call_keyword_count", "C")
            func = self._read_expression()
            args = [self._read_expression() for _ in range(arg_count)]
            keywords = []
            for _ in range(kw_count):
                keyword_name = self._next_payload("call_keyword_name", "I")
                keywords.append(ast.keyword(arg=keyword_name, value=self._read_expression()))
            return ast.Call(func=func, args=args, keywords=keywords)
        if key == "structure:qualifier":
            self._state.expect_token("structure:qualifier")
            attr_name = self._next_payload("attribute_name", "I")
            value = self._read_expression()
            return ast.Attribute(value=value, attr=attr_name, ctx=ast.Load())
        if key == "structure:spread":
            self._state.expect_token("structure:spread")
            value = self._read_expression()
            slice_expr = self._read_expression()
            return ast.Subscript(value=value, slice=slice_expr, ctx=ast.Load())
        if key == "meta:unknown":
            self._state.expect_token("meta:unknown")
            _ = self._next_payload("unknown_expression", "R")
            return ast.Constant(value=None)
        self._state.expect_token(key)
        return ast.Constant(value=None)

    def _read_literal(self) -> ast.Constant:
        key = self._state.next_token_key()
        channel = self._literal_channel_for_key(key)
        entry, data = self._state.consume_with_entry("literal", channel, kind=key)
        kind = entry.kind or key
        literals = self.language_profile.literal_profile
        value: Any
        value = data.get("value") if isinstance(data, dict) else data
        if kind == literals.bool_true:
            return ast.Constant(True)
        if kind == literals.bool_false:
            return ast.Constant(False)
        if kind == literals.null:
            return ast.Constant(None)
        if kind in {literals.string, literals.wide_string}:
            return ast.Constant(str(value) if value is not None else "")
        if kind == literals.bytes:
            blob = value if isinstance(value, str) else ""
            return ast.Constant(bytes.fromhex(blob))
        if kind == literals.integer:
            return ast.Constant(int(value))
        if kind == literals.floating:
            return ast.Constant(float(value))
        return ast.Constant(value)

    def _literal_channel_for_key(self, key: str) -> str:
        literals = self.language_profile.literal_profile
        if key in {literals.string, literals.wide_string, literals.bytes}:
            return "S"
        if key in {literals.bool_true, literals.bool_false}:
            return "C"
        if key == literals.integer:
            return "N"
        return "R"

    def _annotation_from_spec(self, spec: Any) -> Any:
        if not spec:
            return None
        key = spec.get("type_key") if isinstance(spec, dict) else None
        name = None
        if key:
            name = self.language_profile.render_type_name(key)
        if name is None:
            name = spec.get("repr") if isinstance(spec, dict) else None
        if name is None:
            return None
        base = ast.Name(id=name, ctx=ast.Load())
        args = []
        if isinstance(spec, dict):
            for arg_spec in spec.get("args", []):
                args.append(self._annotation_from_spec(arg_spec))
        args = [arg for arg in args if arg is not None]
        if not args:
            return base
        slice_expr = args[0] if len(args) == 1 else ast.Tuple(elts=args, ctx=ast.Load())
        return ast.Subscript(value=base, slice=slice_expr, ctx=ast.Load())
