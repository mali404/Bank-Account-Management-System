"""Process settings read from the environment.

Defaults are chosen to be safe: network egress for LLM calls is disabled unless
explicitly enabled (see §15, the ``egress`` network, and §17 safety).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    """Common runtime settings shared by the testbed services."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # Safety: the simulation has no internet egress by default. Only the agent
    # gateway may reach a hosted LLM API, and only when this is explicitly set.
    allow_llm_egress: bool = False

    # Structured logging verbosity.
    log_level: str = "INFO"

    # Deterministic seeding for reproducible scenario runs.
    seed: int = 42


def get_settings() -> Settings:
    """Construct a :class:`Settings` from the current environment."""
    return Settings()
