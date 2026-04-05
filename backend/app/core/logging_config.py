import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Create base log entry
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        extra = getattr(record, "extra", None)
        if extra and isinstance(extra, dict):
            log_entry.update(extra)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging() -> logging.Logger:
    """Setup structured logging configuration."""

    # Create logs directory if it doesn't exist
    logs_dir = Path(__file__).resolve().parents[3] / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Get log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create formatter based on settings
    if settings.log_format == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler for production
    if settings.is_production:
        file_handler = logging.FileHandler(logs_dir / "nave_api.log")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Create application logger
    logger = logging.getLogger("nave_api")
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(f"nave_api.{name}")
