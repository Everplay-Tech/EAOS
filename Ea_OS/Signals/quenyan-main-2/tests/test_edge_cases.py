import ast
import textwrap

import pytest

from qyn1.encoder import QYNEncoder
from qyn1.decoder import QYNDecoder


def _round_trip(source: str) -> ast.Module:
    encoder = QYNEncoder()
    stream = encoder.encode(source)
    decoder = QYNDecoder(stream.dictionary, stream.tokens, stream.payloads)
    module = decoder.decode()
    assert isinstance(module, ast.Module)
    return module


@pytest.mark.parametrize("value", range(110))
def test_numeric_assignment_variants(value: int) -> None:
    module = _round_trip(f"x_{value} = {value}\n")
    assign = module.body[0]
    assert isinstance(assign, ast.Assign)
    target = assign.targets[0]
    assert isinstance(target, ast.Name)
    assert target.id == f"x_{value}"


def test_empty_file_round_trip() -> None:
    module = _round_trip("\n")
    assert module.body == []


def test_comments_only_round_trip() -> None:
    module = _round_trip("# Comment only\n# Another comment\n")
    assert len(module.body) == 0


def test_unicode_identifiers_round_trip() -> None:
    module = _round_trip("π = 3.14159\n你好 = 'world'\n")
    ids = {node.targets[0].id for node in module.body if isinstance(node, ast.Assign)}
    assert {"π", "你好"} <= ids


def test_deeply_nested_structure() -> None:
    depth = 150
    call_chain = "value"
    for _ in range(depth):
        call_chain = f"wrap({call_chain})"
    source = textwrap.dedent(
        """
        def sample(value):
            def wrap(x):
                return x
            return {}
        """
    ).format(call_chain)
    module = _round_trip(source)
    func = module.body[0]
    assert isinstance(func, ast.FunctionDef)
    return_stmt = func.body[-1]
    assert isinstance(return_stmt, ast.Return)
    expr = return_stmt.value
    depth_seen = 0
    while isinstance(expr, ast.Call):
        depth_seen += 1
        assert expr.func.id == "wrap"  # type: ignore[attr-defined]
        expr = expr.args[0]
    assert depth_seen == depth


def test_very_long_line() -> None:
    payload = "a = '" + ("x" * 1_100_000) + "'\n"
    module = _round_trip(payload)
    assign = module.body[0]
    assert isinstance(assign, ast.Assign)


def test_large_synthetic_module() -> None:
    lines = [f"value_{i} = {i} * {i + 1}\n" for i in range(120_000)]
    source = "".join(lines)
    encoder = QYNEncoder()
    stream = encoder.encode(source)
    decoder = QYNDecoder(stream.dictionary, stream.tokens, stream.payloads)
    module = decoder.decode()
    assert len(module.body) == 120_000


def test_adversarial_repetition() -> None:
    pattern = "result = (a + b) * (c - d) / (e + f)\n"
    source = pattern * 2048
    module = _round_trip(source)
    assert len(module.body) == 2048


@pytest.mark.parametrize(
    "source",
    [
        "def broken(:\n",
        "class Foo(\n    pass",
    ],
)
def test_malformed_inputs_raise(source: str) -> None:
    encoder = QYNEncoder()
    with pytest.raises(SyntaxError):
        encoder.encode(source)


def test_binary_input_raises() -> None:
    encoder = QYNEncoder()
    with pytest.raises((TypeError, SyntaxError)):
        encoder.encode(b"\xff\xfe\xfd")
