"""Resolve NAVE's shared data root independently of the active worktree."""

from __future__ import annotations

import os
from pathlib import Path


DATA_ROOT_ENV = "NAVE_DATA_ROOT"


def canonical_data_root(*, worktree_root: Path, configured_root: Path | None = None) -> Path:
    """Return the stable repository data root, not ``cwd / data``.

    ``NAVE_DATA_ROOT`` or ``configured_root`` wins.  For a linked Git
    worktree, the common repository root is recovered from its ``.git`` file,
    so ignored research data remains shared without being copied into every
    worktree.  Callers should fail loudly when the returned root is absent.
    """

    if configured_root is not None:
        return configured_root.expanduser().resolve()
    configured = os.environ.get(DATA_ROOT_ENV)
    if configured:
        return Path(configured).expanduser().resolve()

    worktree_root = worktree_root.expanduser().resolve()
    git_marker = worktree_root / ".git"
    if git_marker.is_file():
        text = git_marker.read_text().strip()
        if text.startswith("gitdir:"):
            gitdir = Path(text.split(":", 1)[1].strip()).expanduser().resolve()
            # .../.git/worktrees/<name> -> repository root.
            if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
                return gitdir.parent.parent.parent / "data"
    return worktree_root / "data"


def resolve_data_path(relative_path: str, *, worktree_root: Path, configured_root: Path | None = None) -> Path:
    """Resolve an artifact beneath the canonical root without fallback search."""

    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("relative_path must remain beneath the canonical data root")
    return canonical_data_root(worktree_root=worktree_root, configured_root=configured_root) / relative
