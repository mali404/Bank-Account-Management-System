"""M7: adapter smokes, the obs overlay, and one span from an agent run."""

from __future__ import annotations

from pathlib import Path

import yaml
from bankbench.adapters.agentdojo.smoke import smoke as agentdojo_smoke
from bankbench.adapters.garak.smoke import smoke as garak_smoke
from bankbench.adapters.inspect.smoke import smoke as inspect_smoke
from bankbench.adapters.promptfoo.smoke import smoke as promptfoo_smoke
from bankbench.adapters.pyrit.smoke import smoke as pyrit_smoke
from bankbench.frameworks.openai_agents import run_rent_task

from agentbank_common.telemetry import finished_spans, reset_spans
from agentbank_gateway.runner import load_tasks, run_task


def test_adapter_smokes() -> None:
    for result in (
        agentdojo_smoke(),
        garak_smoke(),
        pyrit_smoke(),
        promptfoo_smoke(),
        inspect_smoke(),
    ):
        assert result["ok"] is True
        assert result["adapter"]


def test_obs_overlay_pins_images_and_localhost(repo_root: Path) -> None:
    raw = yaml.safe_load((repo_root / "deploy" / "compose.obs.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    services = raw["services"]
    assert isinstance(services, dict)
    for name in ("otel-collector", "jaeger", "opensearch", "prometheus"):
        assert name in services
        image = str(services[name]["image"])
        assert ":" in image
        assert not image.endswith(":latest")
    ports = services["jaeger"].get("ports") or []
    assert ports == ["127.0.0.1:16686:16686"]


def test_openai_agents_sdk_runs_the_rent_task() -> None:
    assert "200000001" in run_rent_task()


def test_agent_run_emits_a_span() -> None:
    reset_spans()
    run_task(load_tasks()[0], "m7-span")
    spans = finished_spans()
    assert spans
    attributes = getattr(spans[-1], "attributes", {})
    assert attributes.get("run_id") == "m7-span"
    assert attributes.get("prompt_hash")
