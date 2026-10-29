"""A tiny registry mapping defense-profile names to factories (SPEC §9).

Defenses D1-D10 register themselves in later milestones; M0 ships only D0.
"""

from __future__ import annotations

from collections.abc import Callable

from .defense import Defense, NoDefense

__all__ = ["available", "get_defense", "register_defense"]

_REGISTRY: dict[str, Callable[[], Defense]] = {}


def register_defense(name: str, factory: Callable[[], Defense]) -> None:
    """Register ``factory`` under ``name`` (overwrites any existing entry)."""
    _REGISTRY[name] = factory


def get_defense(name: str) -> Defense:
    """Construct the defense registered under ``name``.

    Raises :class:`KeyError` if the profile is unknown.
    """
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown defense profile: {name!r}") from exc
    return factory()


def available() -> list[str]:
    """Return the sorted names of registered defense profiles."""
    return sorted(_REGISTRY)


register_defense("D0", NoDefense)
