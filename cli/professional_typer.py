"""Global CLI interaction wrapper for consistent command UX.

Provides a Typer subclass that automatically prints command start/success/fail
status lines with elapsed time to stderr.
"""

from __future__ import annotations

import os
import time
from functools import wraps
from typing import Any, Callable

import click
import typer

class ProfessionalTyper(typer.Typer):
    """Typer app with automatic, consistent command status output."""

    def command(self, *args: Any, **kwargs: Any):
        register = super().command(*args, **kwargs)

        def decorator(func: Callable[..., Any]):
            @wraps(func)
            def wrapped(*f_args: Any, **f_kwargs: Any):
                if not _status_enabled():
                    return func(*f_args, **f_kwargs)

                label = _command_label(func)
                start = time.perf_counter()
                typer.echo(f"[ ... ] {label}", err=True)
                try:
                    result = func(*f_args, **f_kwargs)
                except Exception:
                    elapsed = time.perf_counter() - start
                    typer.echo(f"[fail] {label} ({elapsed:.2f}s)", err=True)
                    raise
                elapsed = time.perf_counter() - start
                typer.echo(f"[ ok ] {label} ({elapsed:.2f}s)", err=True)
                return result

            return register(wrapped)

        return decorator


def _status_enabled() -> bool:
    raw = os.getenv("NAVE_CLI_STATUS", "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _command_label(func: Callable[..., Any]) -> str:
    ctx = click.get_current_context(silent=True)
    if ctx is not None and ctx.command_path:
        return f"Running {ctx.command_path}"
    return f"Running {func.__name__.replace('_', '-') }"
