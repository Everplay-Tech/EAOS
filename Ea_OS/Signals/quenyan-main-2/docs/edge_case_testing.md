# Edge Case Testing Strategy

To complement the benchmark suite, we added a dedicated stress harness that verifies the
encoder and decoder across adversarial inputs. Tests reside in `tests/test_edge_cases.py`
and cover the following scenarios:

- Empty files and files containing only comments.
- Extremely long lines (1M+ characters) to validate streaming behaviour.
- Deeply nested statements (100+ levels) produced via code generation.
- Non-ASCII identifiers and string literals covering multiple Unicode planes.
- Malformed inputs (syntax errors, binary blobs) to ensure graceful failure.
- Large synthetic modules (~8MB) that force the chunked back-end to trigger.
- Randomised arithmetic expressions (100+ permutations) to exercise the token cache.

The suite encodes each sample, decodes it back to an AST, and verifies structural
properties while asserting that invalid inputs raise predictable exceptions. Peak memory
usage is observed indirectly via the benchmark harness.

These tests run automatically under `pytest` and provide coverage for the stress cases
described in the prompt.
