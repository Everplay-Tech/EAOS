"""Project-level compression planning utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence

from .compression_config import CompressionConfig
from .encoder import EncodedStream, QYNEncoder
from .payloads import Payload
from .string_table import StringTable
from .token_optimisation import TokenOptimisationPlan, build_frequency_plan


@dataclass
class ProjectCompressionAssets:
    """Shared resources used to encode multiple files consistently."""

    string_table: StringTable | None
    token_plan: TokenOptimisationPlan | None


@dataclass
class ProjectEncodingPlan:
    """Analysis result for a set of files under a specific configuration."""

    streams: Dict[Path, EncodedStream]
    assets: ProjectCompressionAssets


class ProjectCompressionPlanner:
    """Analyse a collection of sources to extract shared compression assets."""

    def __init__(
        self, config: CompressionConfig, *, encoder_factory: Callable[[], QYNEncoder] = QYNEncoder
    ) -> None:
        self._config = config
        self._encoder_factory = encoder_factory

    def prepare(self, sources: Iterable[Path]) -> ProjectEncodingPlan:
        streams: Dict[Path, EncodedStream] = {}
        payloads: List[Payload] = []
        global_tokens: List[int] = []
        encoder = self._encoder_factory()
        for path in sources:
            source = path.read_bytes()
            stream = encoder.encode(source)
            streams[path] = stream
            payloads.extend(stream.payloads)
            if self._config.token_optimisation == "project":
                global_tokens.extend(stream.tokens)
        string_table = None
        if self._config.shared_string_table:
            string_table = StringTable.build_from_payloads(payloads)
        token_plan = None
        if self._config.token_optimisation == "project":
            token_plan = build_frequency_plan(global_tokens)
        return ProjectEncodingPlan(
            streams=streams,
            assets=ProjectCompressionAssets(
                string_table=string_table,
                token_plan=token_plan,
            ),
        )


__all__ = [
    "ProjectCompressionAssets",
    "ProjectCompressionPlanner",
    "ProjectEncodingPlan",
]
