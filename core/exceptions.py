"""Application-level exception hierarchy for Nave."""


class NaveCliError(Exception):
    """Base exception for CLI and integration errors."""


class HermesIntegrationError(NaveCliError):
    """Raised when Hermes integration tool dispatch fails."""
