"""LangGraph entry point. Tasks run through the shared gateway graph."""

from agentbank_gateway.runner import RunResult, load_tasks, run_task

AGENT = "ppa"


def run(task_id: str, run_id: str) -> RunResult:
    task = next(item for item in load_tasks() if item.task_id == task_id and item.agent == AGENT)
    return run_task(task, run_id)
