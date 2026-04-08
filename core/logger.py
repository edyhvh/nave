"""Lightweight logging helpers for CLI and integrations."""

from __future__ import annotations

import logging


def configure_logger(name: str, *, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger with a consistent message format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
