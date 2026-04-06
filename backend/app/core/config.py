"""Application configuration using pydantic-settings.

All values can be overridden via environment variables or a .env file.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Nave API"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", alias="NAVE_ENV")
    debug: bool = False

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = True

    # Logging
    log_level: str = "INFO"
    log_format: str = "text"  # "text" | "json"

    # CORS
    allowed_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    allow_credentials: bool = True
    allow_methods: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers: List[str] = ["Content-Type", "Authorization", "X-Requested-With"]

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds

    # Cache
    cache_db_path: str = str(Path.home() / ".cache" / "nave" / "api_cache.db")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


settings = Settings()
