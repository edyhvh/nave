"""Shared prompt utilities for CLI commands."""

from __future__ import annotations

from typing import Optional

import typer


def select_option(label: str, choices: list[str], default: Optional[str] = None) -> str:
    """Use an interactive selector when available, otherwise fallback to numbered input."""
    try:
        import questionary

        answer = questionary.select(
            label,
            choices=choices,
            default=default,
            qmark=">",
            pointer=">",
        ).ask()
        if answer:
            return str(answer)
    except ImportError:
        pass

    typer.echo(label)
    for idx, value in enumerate(choices, start=1):
        typer.echo(f"  {idx}. {value}")
    selected = typer.prompt("Choose option", default="1")
    try:
        index = int(selected) - 1
    except ValueError as exc:
        raise typer.BadParameter("Selection must be a number") from exc
    if index < 0 or index >= len(choices):
        raise typer.BadParameter("Invalid selection")
    return choices[index]


def prompt_float(label: str, default: Optional[float] = None, min_value: float = 0.0) -> float:
    """Prompt for numeric input until it validates as a float and satisfies min_value."""
    while True:
        value = typer.prompt(label, default=default)
        try:
            result = float(value)
        except (TypeError, ValueError):
            typer.echo("Please provide a numeric value.")
            continue
        if result < min_value:
            typer.echo(f"Value must be >= {min_value}")
            continue
        return result
