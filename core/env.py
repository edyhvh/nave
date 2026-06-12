"""Load repository .env once for CLI and trading modules."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOTENV_LOADED = False


def repo_root() -> Path:
    return _REPO_ROOT


def load_repo_dotenv() -> None:
    """Best-effort load of ``<repo>/.env``. Idempotent."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return

    env_path = _REPO_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
        except ImportError:
            pass
        else:
            load_dotenv(env_path)

    _DOTENV_LOADED = True
