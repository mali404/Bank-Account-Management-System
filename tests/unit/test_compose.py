"""Static checks on deploy/compose.yaml (SPEC §14, §15). Parsed with PyYAML; no
docker required."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REQUIRED_SERVICES = ["postgres", "nats", "keycloak", "step-ca"]
REQUIRED_NETWORKS = ["edge", "bank-net", "switch-net", "agent-net", "egress"]
INTERNAL_NETWORKS = ["bank-net", "switch-net", "agent-net"]


@pytest.fixture(scope="module")
def compose(repo_root: Path) -> dict[str, Any]:
    data = yaml.safe_load((repo_root / "deploy" / "compose.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_required_services_present(compose: dict[str, Any]) -> None:
    services = compose["services"]
    for svc in REQUIRED_SERVICES:
        assert svc in services, f"missing service {svc}"


def test_every_service_has_healthcheck(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        assert "healthcheck" in svc, f"service {name} has no healthcheck"
        assert "test" in svc["healthcheck"], f"service {name} healthcheck has no test"


def test_published_ports_bind_localhost(compose: dict[str, Any]) -> None:
    published = 0
    for name, svc in compose["services"].items():
        for port in svc.get("ports", []):
            assert isinstance(port, str), f"{name}: use long/explicit 127.0.0.1 port strings"
            assert port.startswith("127.0.0.1:"), f"{name}: port {port} not bound to localhost"
            published += 1
    assert published > 0, "expected at least one host-published port in M0"


def test_no_latest_image_tags(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        image = svc["image"]
        tag = image.rsplit("/", 1)[-1]
        assert ":" in tag, f"{name}: image {image!r} is not tag-pinned"
        assert not image.endswith(":latest"), f"{name}: image {image!r} uses :latest"


def test_networks_defined(compose: dict[str, Any]) -> None:
    networks = compose["networks"]
    for net in REQUIRED_NETWORKS:
        assert net in networks, f"missing network {net}"


def test_internal_networks_are_internal(compose: dict[str, Any]) -> None:
    networks = compose["networks"]
    for net in INTERNAL_NETWORKS:
        assert (networks[net] or {}).get("internal") is True, f"{net} should be internal"


def test_egress_attached_to_no_service(compose: dict[str, Any]) -> None:
    for name, svc in compose["services"].items():
        assert "egress" not in svc.get("networks", []), f"{name} must not be on egress in M0"


def _volume_targets(svc: dict[str, Any]) -> list[str]:
    """Return the in-container mount targets of a service's volumes."""
    targets: list[str] = []
    for vol in svc.get("volumes", []):
        if isinstance(vol, str):
            # "<source>:<target>[:<opts>]"
            parts = vol.split(":")
            if len(parts) >= 2:
                targets.append(parts[1])
        elif isinstance(vol, dict) and "target" in vol:
            targets.append(str(vol["target"]))
    return targets


def test_step_ca_secrets_not_mounted_over(compose: dict[str, Any]) -> None:
    # `step ca init` must be able to write keys and the password into
    # /home/step/secrets; bind-mounting anything over it breaks init and is not
    # portable across host UIDs. The only mount step-ca gets is its data volume.
    step_ca = compose["services"]["step-ca"]
    for target in _volume_targets(step_ca):
        assert not target.startswith("/home/step/secrets"), (
            f"nothing may be mounted over /home/step/secrets (found {target})"
        )


def test_step_ca_gets_init_password(compose: dict[str, Any]) -> None:
    env = compose["services"]["step-ca"]["environment"]
    # Password supplied non-interactively from .env; no password *file* is used.
    assert "DOCKER_STEPCA_INIT_PASSWORD" in env
    assert "STEPCA_INIT_PASSWORD" in str(env["DOCKER_STEPCA_INIT_PASSWORD"])
    assert "DOCKER_STEPCA_INIT_PASSWORD_FILE" not in env
