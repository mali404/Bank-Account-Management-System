"""Tests for environment-backed settings and their safe defaults."""

from __future__ import annotations

import pytest

from agentbank_common.settings import Settings, get_settings


def test_egress_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOW_LLM_EGRESS", raising=False)
    assert get_settings().allow_llm_egress is False


def test_settings_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_LLM_EGRESS", "true")
    monkeypatch.setenv("SEED", "7")
    settings = Settings()
    assert settings.allow_llm_egress is True
    assert settings.seed == 7
