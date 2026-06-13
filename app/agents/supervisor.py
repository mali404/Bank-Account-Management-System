"""LangGraph supervisor with role-specialized agents.

State flows through one of five role nodes; tools available at each node
are gated by `TOOLS_BY_ROLE`. Reasoning is bounded by `agent_max_steps`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.settings import get_settings
from app.tools.banking_tools import TOOLS_BY_ROLE

PROMPTS_DIR = Path(__file__).parent / "prompts"


class AgentState(TypedDict, total=False):
    user_id: str
    role: str
    messages: Annotated[list[BaseMessage], add_messages]
    needs_approval: bool
    actions_taken: list[dict]


def _llm():
    s = get_settings()
    return ChatOllama(
        base_url=s.ollama_base_url,
        model=s.llm_model,
        temperature=s.llm_temperature,
        num_predict=s.llm_max_tokens,
    )


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


def _make_role_agent(role_key: str, prompt_file: str):
    """Returns a LangGraph React-style agent for one role."""
    llm = _llm()
    tools = TOOLS_BY_ROLE.get(role_key, [])
    system_prompt = _load_prompt(prompt_file)
    return create_agent(model=llm, tools=tools, prompt=system_prompt)


# Role agents — built once per process.
ROLE_AGENTS = {
    "customer":           _make_role_agent("customer", "customer"),
    "teller":             _make_role_agent("teller", "teller"),
    "loan_officer":       _make_role_agent("loan_officer", "loan_officer"),
    "compliance_officer": _make_role_agent("compliance_officer", "compliance"),
    "admin":              _make_role_agent("admin", "admin"),
}


def _route_by_role(state: AgentState) -> Literal[
    "customer", "teller", "loan_officer", "compliance_officer", "admin"
]:
    role = state["role"]
    if role in ROLE_AGENTS:
        return role  # type: ignore[return-value]
    # Fallback — if a future role appears, route to customer (least privilege).
    return "customer"


async def _delegate(state: AgentState, role_key: str) -> AgentState:
    """Invoke the role-agent and merge its messages back."""
    agent = ROLE_AGENTS[role_key]
    result = await agent.ainvoke({"messages": state["messages"]})
    new_messages = result.get("messages", [])
    # Track actions: any tool message with structured result counts.
    actions = list(state.get("actions_taken", []))
    for msg in new_messages:
        if getattr(msg, "type", None) == "tool":
            actions.append({"tool": getattr(msg, "name", "?"), "content": str(msg.content)[:500]})
    return {
        "messages": new_messages,
        "actions_taken": actions,
    }


async def _customer(state: AgentState) -> AgentState: return await _delegate(state, "customer")
async def _teller(state: AgentState) -> AgentState: return await _delegate(state, "teller")
async def _loan(state: AgentState) -> AgentState: return await _delegate(state, "loan_officer")
async def _compliance(state: AgentState) -> AgentState: return await _delegate(state, "compliance_officer")
async def _admin(state: AgentState) -> AgentState: return await _delegate(state, "admin")


def build_supervisor():
    """Compile the supervisor graph. In production we'd attach a
    PostgresSaver checkpointer; for the sample we use an in-memory checkpointer
    so the system runs anywhere."""
    from langgraph.checkpoint.memory import MemorySaver

    builder = StateGraph(AgentState)
    builder.add_node("customer",           _customer)
    builder.add_node("teller",             _teller)
    builder.add_node("loan_officer",       _loan)
    builder.add_node("compliance_officer", _compliance)
    builder.add_node("admin",              _admin)

    builder.add_conditional_edges(
        START,
        _route_by_role,
        {
            "customer":           "customer",
            "teller":             "teller",
            "loan_officer":       "loan_officer",
            "compliance_officer": "compliance_officer",
            "admin":              "admin",
        },
    )
    for n in ("customer", "teller", "loan_officer", "compliance_officer", "admin"):
        builder.add_edge(n, END)

    return builder.compile(checkpointer=MemorySaver())


def initial_state(user_id: str, role: str, user_message: str) -> AgentState:
    return AgentState(
        user_id=user_id,
        role=role,
        messages=[HumanMessage(content=user_message)],
        actions_taken=[],
    )
