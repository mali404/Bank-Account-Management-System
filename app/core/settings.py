"""Typed application settings, hydrated from environment variables."""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level config. Uses pydantic-settings to read .env / process env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_env: Literal["local", "test", "staging", "prod"] = "local"
    app_host: str = "0.0.0.0"  # noqa: S104  intentional for container
    app_port: int = 8000
    log_level: str = "INFO"

    # Database
    database_url: str
    database_sync_url: str
    database_admin_url: str

    # Crypto / secrets
    jwt_private_key_path: Path
    jwt_public_key_path: Path
    jwt_algorithm: str = "RS256"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7
    audit_hmac_key_path: Path
    db_column_dek_path: Path

    # LLM / agents
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b-instruct-q4_K_M"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    agent_max_steps: int = 12
    agent_max_tool_calls: int = 6

    # Observability
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agentic-bank"
    prometheus_enabled: bool = True

    # Rate limiting
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_default: str = "60/minute"

    # Business
    high_value_threshold: Decimal = Field(default=Decimal("5000.00"))

    # Internal API client (loopback) — used by agent tools to call the API as a
    # well-typed contract rather than touching DB directly.
    internal_api_base: str = "http://localhost:8000"

    def read_secret(self, path: Path) -> SecretStr:
        """Read a secret file. Raises FileNotFoundError loudly — fail closed."""
        return SecretStr(path.read_text().strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor; instantiate once per process."""
    return Settings()  # type: ignore[call-arg]
