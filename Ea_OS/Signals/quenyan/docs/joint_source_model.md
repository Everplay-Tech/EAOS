# Joint Source Model for Morpheme Streams

## Overview
This note formalizes the joint distribution over morpheme tokens and their payloads. The model captures how token classes deterministically constrain payload types, enabling downstream compressors and validators to reason about structured code streams.

## Alphabets
- Let $\Sigma$ be the finite morpheme vocabulary (≈230 tokens, such as `construct:*`, `op:*`, `literal:*`, `structure:*`, `meta:*`, and `modifier:*`).
- Let $Y$ be the disjoint union of all payload domains:
  - $Y_{id}$: identifier indices into the string table.
  - $Y_{str}$: string literal indices.
  - $Y_{num}$: integer literals and counts (e.g., `statement_count`, `arg_count`, `body_length`).
  - $Y_{bool}$: boolean flags (e.g., `async?`, `has_value?`).
  - $Y_{other}$: structured meta payloads (e.g., `import_spec`, `unknown_tag`).
- Introduce the distinguished symbol $\bot$ representing the absence of a payload.
- For each position $i$ in the stream, $T_i \in \Sigma$ and $P_i \in Y \cup \{\bot\}$.
- In practice:
  - Tokens such as `structure:identifier`, `literal:*`, `meta:unknown`, and most `meta:/header` tokens carry payloads.
  - Structural tokens such as `construct:function`, `construct:if`, and `op:assign` usually omit payloads; their children encode the associated information.

## Payload Classes
Define a payload-class variable $C$ with the following cases:
- $C = \text{NONE}$ when $P = \bot$.
- $C = \text{ID}$ for identifier indices.
- $C = \text{STR}$ for string literals.
- $C = \text{NUM}$ for numeric literals and counts.
- $C = \text{BOOL}$ for flags.
- $C = \text{OTHER}$ for structured meta payloads (e.g., import specifications or unknown tags).

The payload class is a deterministic function of the token: $C_i = f(T_i)$. Examples include:
- If $T_i = \text{structure:identifier}$, then $C_i = \text{ID}$.
- If $T_i = \text{literal:int}$, then $C_i = \text{NUM}$.
- If $T_i = \text{flow:return}$, then $C_i = \text{BOOL}$ (e.g., the presence of a `has_value` flag).

## Joint Source Process
We model the stream as the stationary empirical distribution over all positions across the corpus:
\[
\{(T_i, C_i, P_i)\}_{i \ge 1}, \quad C_i = f(T_i), \quad P_i \in Y_{C_i} \cup \{\bot\}.
\]

This representation makes explicit that token identity fully determines the payload class, while the payload value (or absence) follows the empirical distribution conditioned on that class. The formulation is suitable for entropy modeling, validation, and schema-aware decoding in production-grade pipelines.
