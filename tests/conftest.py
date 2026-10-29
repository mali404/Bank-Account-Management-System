"""Shared fixtures and Hypothesis profiles.

Two Hypothesis profiles are registered:

* ``ci`` (default) — 1,000 examples, no deadline, fixed seed so CI is
  deterministic. This is the ISO M1 acceptance profile and the one ``make test``
  uses.
* ``dev`` — 100 examples for a faster local loop.

Select a profile with ``HYPOTHESIS_PROFILE=dev`` (defaults to ``ci``).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, Phase, settings

REPO_ROOT = Path(__file__).resolve().parents[1]

CI_MAX_EXAMPLES = 1000

settings.register_profile(
    "ci",
    max_examples=CI_MAX_EXAMPLES,
    deadline=None,
    derandomize=True,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow],
    phases=(Phase.explicit, Phase.reuse, Phase.generate, Phase.target),
)
settings.register_profile(
    "dev",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT
