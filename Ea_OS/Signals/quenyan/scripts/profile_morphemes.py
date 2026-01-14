"""Profile morpheme frequency distributions across language corpora."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qyn1.dictionary import MorphemeDictionary, load_dictionary
from qyn1.encoder import QYNEncoder

SUPPORTED_LANGUAGES = {"python", "javascript", "go", "typescript"}
PREENCODED_SUFFIXES = {".morpheme.json", ".qyn.json", ".tokens.json"}
DEFAULT_SEQUENCE_LENGTH = 3


class StreamCollectionError(RuntimeError):
    """Raised when the input manifest cannot be processed."""


def parse_inputs(raw_inputs: List[str]) -> Dict[str, List[Path]]:
    datasets: Dict[str, List[Path]] = {}
    for item in raw_inputs:
        if "=" not in item:
            raise StreamCollectionError(
                f"Invalid dataset specification '{item}'. Expected format 'language=path'."
            )
        language, raw_path = item.split("=", 1)
        language = language.lower()
        if language not in SUPPORTED_LANGUAGES:
            raise StreamCollectionError(f"Unsupported language '{language}'")
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise StreamCollectionError(f"Input path '{path}' does not exist")
        datasets.setdefault(language, []).append(path)
    return datasets


def iter_python_streams(paths: List[Path], encoder: QYNEncoder) -> Iterator[Tuple[List[int], str]]:
    for root in paths:
        if root.is_dir():
            for file in root.rglob("*.py"):
                if file.name.startswith(".") or "__pycache__" in file.parts:
                    continue
                yield _encode_python_file(file, encoder)
        elif root.suffix == ".py":
            yield _encode_python_file(root, encoder)
        else:
            raise StreamCollectionError(f"Unsupported Python input: {root}")


def _encode_python_file(path: Path, encoder: QYNEncoder) -> Tuple[List[int], str]:
    source = path.read_text(encoding="utf-8")
    stream = encoder.encode(source)
    return stream.tokens, stream.dictionary_version


def iter_preencoded_streams(paths: List[Path]) -> Iterator[Tuple[List[int], str]]:
    for root in paths:
        if root.is_dir():
            for file in root.rglob("*.json"):
                if file.suffixes[-2:] and "".join(file.suffixes[-2:]) in PREENCODED_SUFFIXES:
                    yield _load_token_file(file)
                elif file.suffix in {".json"} and file.name.endswith(tuple(PREENCODED_SUFFIXES)):
                    yield _load_token_file(file)
        elif root.suffix in {".json"}:
            yield _load_token_file(root)
        else:
            raise StreamCollectionError(
                f"Unsupported non-Python dataset entry '{root}'. Provide morpheme JSON exports."
            )


def _load_token_file(path: Path) -> Tuple[List[int], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "tokens" not in data:
        raise StreamCollectionError(f"Token file '{path}' does not contain 'tokens' field")
    tokens = list(map(int, data["tokens"]))
    version = str(data.get("dictionary_version", "1.0"))
    return tokens, version


def entropy(counter: Counter[int]) -> float:
    total = sum(counter.values())
    if total == 0:
        return 0.0
    result = 0.0
    for count in counter.values():
        probability = count / total
        result -= probability * math.log2(probability)
    return result


def conditional_entropy(trigram_counter: Counter[Tuple[int, int, int]]) -> float:
    """Compute H(T_i | T_{i-1}, T_{i-2}) for a trigram distribution."""

    total = sum(trigram_counter.values())
    if total == 0:
        return 0.0

    context_totals: Counter[Tuple[int, int]] = Counter()
    context_counts: Dict[Tuple[int, int], Counter[int]] = {}
    for (a, b, c), count in trigram_counter.items():
        context = (a, b)
        context_totals[context] += count
        if context not in context_counts:
            context_counts[context] = Counter()
        context_counts[context][c] += count

    entropy_bits = 0.0
    for context, next_counts in context_counts.items():
        context_total = context_totals[context]
        context_probability = context_total / total
        context_entropy = 0.0
        for count in next_counts.values():
            probability = count / context_total
            context_entropy -= probability * math.log2(probability)
        entropy_bits += context_probability * context_entropy
    return entropy_bits


def describe_sequences(
    sequence_counter: Counter[Tuple[int, ...]],
    dictionary: MorphemeDictionary,
    limit: int,
) -> List[Dict[str, object]]:
    items = sequence_counter.most_common(limit)
    output: List[Dict[str, object]] = []
    for indices, count in items:
        entries = [dictionary.entry_for_index(index) for index in indices]
        output.append(
            {
                "indices": list(indices),
                "keys": [entry.key for entry in entries],
                "morphemes": [entry.morpheme for entry in entries],
                "count": count,
            }
        )
    return output


def describe_frequency(
    counter: Counter[int], dictionary: MorphemeDictionary, limit: int
) -> List[Dict[str, object]]:
    total = sum(counter.values())
    entries = []
    for index, count in counter.most_common(limit):
        entry = dictionary.entry_for_index(index)
        entries.append(
            {
                "index": index,
                "key": entry.key,
                "morpheme": entry.morpheme,
                "count": count,
                "probability": count / total if total else 0.0,
            }
        )
    return entries


def profile_language(
    language: str,
    paths: List[Path],
    dictionaries: Dict[str, MorphemeDictionary],
    sequence_length: int,
    top_n: int,
) -> Dict[str, object]:
    token_counter: Counter[int] = Counter()
    sequence_counter: Counter[Tuple[int, ...]] = Counter()
    trigram_counter: Counter[Tuple[int, int, int]] = Counter()
    stream_count = 0
    dictionary_version = "1.0"

    if language == "python":
        encoder = QYNEncoder()
        iterator = iter_python_streams(paths, encoder)
    else:
        iterator = iter_preencoded_streams(paths)

    for tokens, version in iterator:
        dictionary_version = version
        dictionaries.setdefault(version, load_dictionary(version))
        dictionary = dictionaries[version]
        token_counter.update(tokens)
        if len(tokens) >= sequence_length:
            for index in range(len(tokens) - sequence_length + 1):
                sequence = tuple(tokens[index : index + sequence_length])
                sequence_counter[sequence] += 1
        if len(tokens) >= 3:
            for index in range(len(tokens) - 2):
                trigram = tuple(tokens[index : index + 3])  # (T_{i-2}, T_{i-1}, T_i)
                trigram_counter[trigram] += 1
        stream_count += 1

    if stream_count == 0:
        return {
            "stream_count": 0,
            "token_count": 0,
            "entropy_bits": 0.0,
            "top_morphemes": [],
            "top_sequences": [],
            "dictionary_version": dictionary_version,
        }

    dictionary = dictionaries[dictionary_version]
    return {
        "stream_count": stream_count,
        "token_count": sum(token_counter.values()),
        "entropy_bits": entropy(token_counter),
        "conditional_entropy_bits": conditional_entropy(trigram_counter),
        "top_morphemes": describe_frequency(token_counter, dictionary, top_n),
        "top_sequences": describe_sequences(sequence_counter, dictionary, top_n),
        "dictionary_version": dictionary_version,
    }


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="LANG=PATH",
        help="Dataset specification (can be provided multiple times)",
    )
    parser.add_argument("--output", required=True, help="Destination JSON file")
    parser.add_argument(
        "--sequence-length",
        type=int,
        default=DEFAULT_SEQUENCE_LENGTH,
        help="Sequence length for common pattern analysis (default: 3)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=25,
        help="Number of entries to emit in frequency and sequence histograms",
    )
    args = parser.parse_args(argv)

    try:
        datasets = parse_inputs(args.input)
    except StreamCollectionError as exc:  # pragma: no cover - CLI guard
        raise SystemExit(str(exc)) from exc

    dictionaries: Dict[str, MorphemeDictionary] = {}
    languages: Dict[str, Dict[str, object]] = {}
    for language, paths in datasets.items():
        languages[language] = profile_language(
            language,
            paths,
            dictionaries,
            args.sequence_length,
            args.top_n,
        )

    summary = {
        "sequence_length": args.sequence_length,
        "top_n": args.top_n,
        "languages": languages,
    }
    Path(args.output).write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    main()
