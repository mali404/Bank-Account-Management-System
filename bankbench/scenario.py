"""Scenario catalog loaded from ``scenarios/Sxx.yaml``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

__all__ = ["Scenario", "load_scenarios"]


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    adversary: str
    channel: str
    target_agent: str
    user_task_id: str
    injection_template: str
    placement: str
    goal: str
    success_oracle: str
    utility_oracle: str
    severity: str
    tags: tuple[str, ...]


def load_scenarios(directory: Path | None = None) -> list[Scenario]:
    root = directory or Path(__file__).resolve().parents[1] / "scenarios"
    found: list[Scenario] = []
    for path in sorted(root.glob("S*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        tags = raw.get("tags") or []
        assert isinstance(tags, list)
        found.append(
            Scenario(
                id=str(raw["id"]),
                title=str(raw["title"]),
                adversary=str(raw["adversary"]),
                channel=str(raw["channel"]),
                target_agent=str(raw["target_agent"]),
                user_task_id=str(raw["user_task_id"]),
                injection_template=str(raw["injection_template"]),
                placement=str(raw["placement"]),
                goal=str(raw["goal"]),
                success_oracle=str(raw["success_oracle"]),
                utility_oracle=str(raw["utility_oracle"]),
                severity=str(raw["severity"]),
                tags=tuple(str(tag) for tag in tags),
            )
        )
    return found
