"""Factories for options services shared by CLI, scripts, and integrations."""

from __future__ import annotations


def build_options_analyzer(*, source: str):
    """Construct an options analyzer while tolerating older test doubles."""
    from options.analyzer import OptionsAnalyzer

    try:
        return OptionsAnalyzer(fetcher_source=source)
    except TypeError:
        return OptionsAnalyzer()
