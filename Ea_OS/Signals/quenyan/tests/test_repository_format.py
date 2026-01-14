from __future__ import annotations

from qyn1.repository import (
    RepositoryWriter,
    diff_repository_indexes,
    load_repository_index,
    sparse_checkout,
)


def test_repository_writer_and_diff(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    source_a = root / "alpha.py"
    source_b = root / "beta.py"
    source_a.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    source_b.write_text("def beta():\n    return 2\n", encoding="utf-8")
    repo_dir = tmp_path / "repo"
    writer = RepositoryWriter(root, repo_dir, compression_mode="balanced", backend="rans")
    writer.add_package(source_a, b"package-alpha")
    writer.add_package(source_b, b"package-beta")
    index = writer.finalise()
    assert (repo_dir / "mirror" / "alpha.py.qyn1").exists()
    assert (repo_dir / "objects").exists()
    index_path = repo_dir / "index.json"
    loaded = load_repository_index(index_path)
    assert len(loaded.entries) == 2

    repo_dir_2 = tmp_path / "repo2"
    writer2 = RepositoryWriter(root, repo_dir_2, compression_mode="balanced", backend="rans")
    writer2.add_package(source_a, b"package-alpha")
    writer2.add_package(source_b, b"package-beta-modified")
    index2 = writer2.finalise()
    diff = diff_repository_indexes(index2, index)
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["changed"] == ["beta.py"]

    checkout = sparse_checkout(index2, repo_dir_2, [source_a.relative_to(root)])
    assert "alpha.py" in checkout
