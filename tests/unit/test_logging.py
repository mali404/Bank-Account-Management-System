"""Tests for structured JSON logging."""

from __future__ import annotations

import json
import logging

from agentbank_common.logging import JsonFormatter, configure_logging, get_logger


def test_json_formatter_emits_valid_json() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.run_id = "r1"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["run_id"] == "r1"


def test_configure_logging_sets_level() -> None:
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    assert get_logger("x").name == "x"
