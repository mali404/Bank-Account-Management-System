"""Run the scenario catalog with the deterministic mock model.

Under D0 the mock follows an injected instruction, so the attack oracle
fires. Any other defense profile leaves the attack flags unset: that is
the mock refusing the injection, not a claim that the profile is
implemented. Benign twins (``injected`` false) keep utility success.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from agentbank_common.oracle import StateSnapshot
from agentbank_common.results_schema import RESULTS_COLUMN_NAMES

from .oracles import evaluate
from .scenario import Scenario, load_scenarios

__all__ = ["ANCHOR_TS", "RunRow", "run_catalog"]

ANCHOR_TS = "2026-10-29T15:00:00Z"

_FLAG_KEY = {
    "posted_transfer": "posted_to_attacker",
    "payee_added": "payee_added",
    "amount_mismatch": "amount_mismatch",
    "unauthorized_transfer": "unauthorized_transfer",
    "adjustment": "adjustment",
    "fraudulent_return": "fraudulent_return",
    "second_transfer": "second_transfer",
    "psp_payment": "psp_payment",
    "broader_consent": "broader_consent",
    "descriptor_changed": "descriptor_changed",
    "cumulative_value": "cumulative_value",
    "limit_bypass": "limit_bypass",
    "held_released": "held_released",
    "confusable_payee": "confusable_payee",
    "unauthorized_action": "unauthorized_action",
    "account_frozen": "account_frozen",
    "wrong_creditor": "wrong_creditor",
}


@dataclass(frozen=True)
class RunRow:
    """One results row, in the stable column order."""

    values: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {name: self.values[name] for name in RESULTS_COLUMN_NAMES}


def run_catalog(
    *,
    seed: int,
    model: str = "mock-local",
    defenses: tuple[str, ...] = ("D0",),
    git_sha: str = "unknown",
    scenarios: list[Scenario] | None = None,
    template_dir: Path | None = None,
) -> list[RunRow]:
    """Return one row per scenario, injection bit, and defense. Order is fixed."""
    catalog = scenarios if scenarios is not None else load_scenarios()
    templates = template_dir or Path(__file__).resolve().parents[1] / "templates" / "injections"
    env = Environment(loader=FileSystemLoader(templates), autoescape=False)
    env.filters["b64"] = _b64
    rows: list[RunRow] = []
    for scenario in catalog:
        for injected in (False, True):
            prompt = _prompt(env, scenario, injected)
            for defense in defenses:
                rows.append(_row(scenario, injected, defense, seed, model, git_sha, prompt))
    return rows


def _b64(value: object) -> str:
    return base64.b64encode(str(value).encode()).decode()


def _prompt(env: Environment, scenario: Scenario, injected: bool) -> str:
    if not injected:
        return scenario.title
    template = env.get_template(scenario.injection_template)
    return template.render(payload=scenario.goal, feedback="held")


def _row(
    scenario: Scenario,
    injected: bool,
    defense: str,
    seed: int,
    model: str,
    git_sha: str,
    prompt: str,
) -> RunRow:
    gullible = injected and defense == "D0"
    state = _snapshot(scenario, gullible)
    attack = evaluate(scenario.success_oracle, state, scenario, None)
    utility = evaluate(scenario.utility_oracle, state, scenario, None)
    leaked = (
        1 if attack.success and scenario.success_oracle in {"canary_egress", "prompt_canary"} else 0
    )
    values: dict[str, object] = {
        "run_id": f"mock-{seed}",
        "ts_utc": ANCHOR_TS,
        "git_sha": git_sha,
        "model": model,
        "model_version": "0",
        "framework": "langgraph",
        "defense_profile": defense,
        "scenario_id": scenario.id,
        "task_id": scenario.user_task_id,
        "template_id": scenario.injection_template if injected else "benign",
        "seed": seed,
        "injected": injected,
        "attack_success": attack.success,
        "utility_success": utility.success,
        "harm": attack.success,
        "utv_usd": 10.0 if attack.success else 0.0,
        "leaked_canaries": leaked,
        "hitl_prompts": 0,
        "hitl_approved": 0,
        "detected": False,
        "tokens_in": len(prompt),
        "tokens_out": 12 if gullible else 8,
        "cost_usd": 0.0,
        "latency_s": round(0.01 + (seed % 7) * 0.001, 4),
        "tool_calls": 1,
        "error": "",
    }
    return RunRow(values)


def _snapshot(scenario: Scenario, gullible: bool) -> StateSnapshot:
    bank: dict[str, object] = {"utility_success": not gullible}
    mail: dict[str, object] = {}
    egress: dict[str, object] = {}
    archive: dict[str, object] = {}
    name = scenario.success_oracle
    if gullible:
        if name == "canary_egress":
            egress["body"] = "CANARY-bank-c-0001"
        elif name == "email_exfil":
            mail["body"] = "transactions to attacker"
        elif name == "prompt_canary":
            archive["text"] = "CANARY-prompt"
        elif name == "undisclosed_transfer":
            bank["transfer_posted"] = True
            bank["disclosed"] = False
        else:
            bank[_FLAG_KEY[name]] = True
    return StateSnapshot(
        bank_db=bank,
        switch_archive=archive,
        mail_outbox=mail,
        psp_egress=egress,
    )
