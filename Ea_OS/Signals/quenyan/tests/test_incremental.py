from __future__ import annotations

from pathlib import Path

from qyn1.compression_config import get_compression_config
from qyn1.incremental import IncrementalEncoder, ManifestDependencyResolver


def _write_sample(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_incremental_encoder_reuses_cache(tmp_path) -> None:
    root = tmp_path
    source_a = root / "a.py"
    source_b = root / "b.py"
    _write_sample(source_a, "from b import helper\ndef call():\n    return helper()\n")
    _write_sample(source_b, "def helper():\n    return 1\n")
    cache_dir = root / ".cache"
    output_dir = root / "out"
    manifest = {"a.py": ["b.py"], "b.py": []}
    resolver = ManifestDependencyResolver(manifest, root)
    config = get_compression_config("balanced")

    encoder = IncrementalEncoder(
        root=root,
        sources=[source_a, source_b],
        output_dir=output_dir,
        cache_dir=cache_dir,
        passphrase="secret",
        compression_config=config,
        dependency_resolver=resolver,
    )
    report_initial = encoder.run()
    assert len(report_initial.encoded) == 2
    assert report_initial.cache_hits == 0

    encoder_second = IncrementalEncoder(
        root=root,
        sources=[source_a, source_b],
        output_dir=output_dir,
        cache_dir=cache_dir,
        passphrase="secret",
        compression_config=config,
        dependency_resolver=resolver,
    )
    report_second = encoder_second.run()
    assert not report_second.encoded
    assert len(report_second.reused) == 2
    assert report_second.cache_hits == 2
    assert report_second.hit_rate() == 1.0

    _write_sample(source_b, "def helper():\n    return 2\n")
    encoder_third = IncrementalEncoder(
        root=root,
        sources=[source_a, source_b],
        output_dir=output_dir,
        cache_dir=cache_dir,
        passphrase="secret",
        compression_config=config,
        dependency_resolver=resolver,
    )
    report_third = encoder_third.run()
    encoded_sources = {result.source.name for result in report_third.encoded}
    assert encoded_sources == {"a.py", "b.py"}
    assert report_third.dependency_rebuilds >= 1
