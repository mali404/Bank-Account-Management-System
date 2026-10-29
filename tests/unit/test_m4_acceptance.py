"""M4 acceptance: six agents finish the benign tasks and every call is traced."""

from __future__ import annotations

from collections import defaultdict

from agentbank_gateway.runner import BENIGN_UTILITY, load_tasks, run_task
from agentbank_gateway.sims import UserSim

AGENTS = ("cba", "ops", "rec", "ppa", "pen", "ins")


def test_each_agent_meets_reference_utility() -> None:
    tasks = load_tasks()
    assert len(tasks) >= 30
    grouped: dict[str, list[bool]] = defaultdict(list)
    for task in tasks:
        result = run_task(task, run_id=f"run-{task.task_id}")
        assert result.success, (task.task_id, result.final, result.traces)
        assert result.traces
        assert all(event.run_id == result.run_id for event in result.traces)
        grouped[task.agent].append(result.success)
    assert set(grouped) == set(AGENTS)
    for agent in AGENTS:
        utility = sum(grouped[agent]) / len(grouped[agent])
        assert utility >= BENIGN_UTILITY


def test_user_sim_models() -> None:
    always = UserSim("always-approve")
    assert always.approve("pay", "T001")
    careful = UserSim("careful")
    assert careful.approve("approve T001", "T001")
    assert careful.approve("approve something else", "T001") is False
    tired = UserSim("fatigue")
    assert tired.approve("1", "T001") is False
    assert tired.approve("2", "T001") is False
    assert tired.approve("3", "T001") is True
