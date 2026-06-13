"""Agent chat endpoint."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.agents.supervisor import build_supervisor, initial_state
from app.api.deps import CurrentUserDep
from app.schemas.api import AgentChatRequest, AgentChatResponse
from app.tools.banking_tools import current_jwt

router = APIRouter(prefix="/agent", tags=["agent"])

# Compile once. The graph is stateless re: user data; per-thread state lives
# in the checkpointer keyed by thread_id.
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_supervisor()
    return _graph


@router.post("/chat", response_model=AgentChatResponse)
async def chat(
    body: AgentChatRequest,
    user: CurrentUserDep,
    request: Request,
) -> AgentChatResponse:
    # Tools call the API on behalf of this user — pass the bearer token in.
    auth = request.headers.get("authorization", "")
    bearer = auth.removeprefix("Bearer ").strip() if auth.lower().startswith("bearer ") else ""
    token_ctx = current_jwt.set(bearer)

    thread_id = body.thread_id or str(uuid.uuid4())
    state = initial_state(user_id=user.user_id, role=user.role.value, user_message=body.message)

    try:
        graph = _get_graph()
        result = await graph.ainvoke(
            state,
            config={"configurable": {"thread_id": thread_id}},
        )
    finally:
        current_jwt.reset(token_ctx)

    last = result["messages"][-1] if result.get("messages") else None
    reply = getattr(last, "content", "") if last else ""

    return AgentChatResponse(
        thread_id=thread_id,
        reply=str(reply),
        actions_taken=result.get("actions_taken", []),
        pending_approval=None,
    )
