"""False-positive rate of a defense on the benign task catalog."""

from __future__ import annotations

from agentbank_gateway import get_defense
from agentbank_gateway.runner import load_tasks, run_task
from agentbank_gateway.sims import UserSim

__all__ = ["false_positive_rate", "false_positive_rates"]


def false_positive_rate(defense_name: str, *, hitl: str = "careful") -> float:
    """Fraction of benign tasks the defense refuses. ``hitl`` selects the user-sim."""
    tasks = load_tasks()
    if not tasks:
        return 0.0
    failed = 0
    for task in tasks:
        result = run_task(
            task,
            f"fp-{defense_name}-{task.task_id}",
            defense=get_defense(defense_name),
            user_sim=UserSim(hitl),
        )
        if not result.success:
            failed += 1
    return failed / len(tasks)


def false_positive_rates(names: tuple[str, ...], *, hitl: str = "careful") -> dict[str, float]:
    return {name: false_positive_rate(name, hitl=hitl) for name in names}
