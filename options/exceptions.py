"""Exception hierarchy for the options module."""

from __future__ import annotations


class OptionsError(Exception):
    """Base exception for options analysis failures."""


class OptionsDataError(OptionsError):
    """Raised when market data cannot be fetched or normalized."""


class OptionsComputationError(OptionsError):
    """Raised when quantitative calculations fail."""


class OptionsStrategyError(OptionsError):
    """Raised when no viable strategy can be generated."""
