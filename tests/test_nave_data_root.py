from pathlib import Path

import pytest

from research.nave.data_root import canonical_data_root, resolve_data_path


def test_linked_worktree_resolves_main_repository_data_root(tmp_path: Path):
    repo = tmp_path / "repo"
    gitdir = repo / ".git" / "worktrees" / "child"
    gitdir.mkdir(parents=True)
    child = tmp_path / "child"
    child.mkdir()
    (child / ".git").write_text(f"gitdir: {gitdir}\n")

    assert canonical_data_root(worktree_root=child) == repo / "data"


def test_configured_root_wins_over_worktree_discovery(tmp_path: Path):
    configured = tmp_path / "shared-data"
    assert canonical_data_root(worktree_root=tmp_path / "child", configured_root=configured) == configured


def test_artifact_resolution_rejects_escape_paths(tmp_path: Path):
    with pytest.raises(ValueError):
        resolve_data_path("../outside.parquet", worktree_root=tmp_path)
