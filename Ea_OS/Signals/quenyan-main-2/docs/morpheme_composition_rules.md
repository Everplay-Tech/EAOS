# Morpheme Composition Rules (PROMPT 1.2.B)

Complex language features are expressed by composing base morphemes emitted from the dictionary.
The encoder adheres to the deterministic grammar below so that every morpheme sequence is
unambiguously decodable and continues to benefit from the frequency-weighted compression model.

## Grammar Overview

```
stream            ::= meta.stream_start header module meta.stream_end
header            ::= meta.version_header meta.dictionary_version
module            ::= construct.module statement_count { statement }
statement         ::= function | import | assignment | return | expression_stmt | fallback
function          ::= construct.function fn_metadata parameter_block body_block
fn_metadata       ::= payload(function_name) payload(function_async?) type_signature
parameter_block   ::= payload(function_arg_count) { structure.parameter payload(parameter_spec) }
body_block        ::= payload(function_body_length) { statement }
assignment        ::= op.assign payload(assign_target_count) { expression } expression
return            ::= flow.return payload(return_has_value) [ expression ]
expression        ::= identifier | literal | call | binop | unary | attribute | subscript | fallback
identifier        ::= structure.identifier payload(identifier)
literal           ::= literal.* payload(literal)
call              ::= op.call payload(call_arg_count) payload(call_keyword_count) expression { expression }
                     { payload(call_keyword_name) expression }
binop             ::= op.* expression expression
unary             ::= op.* expression
attribute         ::= structure.qualifier payload(attribute_name) expression
subscript         ::= structure.spread expression expression
fallback          ::= meta.unknown payload(unknown_*)
```

All payload markers refer to typed entries in the accompanying morpheme stream. For example,
`payload(function_return)` carries a nested structure describing the return type; the decoder can
reconstruct complex annotations purely from payload data without emitting auxiliary markers.

## Type Composition

Type annotations are represented by a recursive payload structure (`type_spec`) that records the
base morpheme key and any generic arguments. Generics are encoded as a pre-order traversal:

1. Emit the parent morpheme key (e.g. `type:array`).
2. Emit `structure:generic` followed by `payload(type_generic_count)`.
3. Recursively encode each type argument using the same scheme.

The decoder consumes the child count to rebuild `ast.Subscript` nodes while preserving order. When a
language-specific identifier does not map to a canonical morpheme, the encoder emits `meta:unknown`
for the type key and stores the textual representation in `payload(type_repr)`; this guarantees
round-tripping even for DSL annotations.

## Modifiers and Qualifiers

Modifier morphemes (prefix `modifier:`) are layered using a left-to-right precedence rule:

1. Access modifiers (`public`, `private`, `protected`, `internal`).
2. Lifetime and storage qualifiers (`static`, `async`, `readonly`, `volatile`).
3. Semantic constraints (`final`, `abstract`, `override`, `sealed`).
4. Generic variance markers (`covariant`, `contravariant`, `invariant`).

When multiple modifiers apply to the same construct the encoder emits them in the order above,
which ensures deterministic reconstruction. For example, a `private static final` method produces
`modifier:private → modifier:static → modifier:final → construct:method` followed by the usual
metadata payloads.

## Async, Await, and Yield

Asynchronous functions set the `function_async` payload flag; resumable expressions rely on
specialised morphemes (`op:await`, `flow:resume`, `flow:suspend`). An “async function” therefore
emits the standard function morpheme plus `function_async = true`. Inside the body the presence of
`op:await` or `flow:yield` morphemes distinguishes coroutine behaviour from synchronous execution.

## Generic Types and Nested Composition

The encoder normalises nested generics using a canonical parenthesisation. For a type such as
`List<Map<String, Integer>>` the emitted sequence is:

```
structure.parameter payload(parameter_spec{name="items", type_key="type:array"})
structure.generic payload(type_generic_count=1)
structure.parameter (implicit from payload) type_key="type:map"
structure.generic payload(type_generic_count=2)
(meta) type argument #1: type_key="type:string"
(meta) type argument #2: type_key="type:int"
```

The payload hierarchy allows the decoder to rebuild the `List`/`Map` AST shape exactly while still
anchoring each component to its morpheme entry.

## Custom Operators and DSL Constructs

Operators that do not have a dedicated morpheme fall back to `meta:unknown` with an explanatory
payload (for example `payload(operator_repr="Spaceship")`). The decoder returns an opaque AST node
annotated with the captured metadata so that downstream tooling can decide how to interpret or
rewrite the construct. Because the fallback morpheme has a reserved high-bit prefix it does not
collide with canonical entries and remains compressible under the ANS model.

## Determinism Guarantees

* **Ordering:** Child counts precede child sequences, making iteration order explicit.
* **Optional fields:** Optional payloads are emitted in every case with explicit boolean flags,
  preventing omission-based ambiguity.
* **Version header:** The morpheme stream begins with `meta:version_header` followed by the encoder
  and dictionary versions, ensuring that future grammar revisions can co-exist with legacy payloads.

These rules guarantee unambiguous decomposition of morpheme streams while keeping token sequences
stable enough for statistical compression.
