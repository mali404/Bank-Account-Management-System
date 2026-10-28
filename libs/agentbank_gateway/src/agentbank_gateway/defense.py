"""The ``Defense`` plugin protocol and the D0 (no-op) baseline (SPEC §9, §19)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import Allow, Decision, Message, RunContext, TaggedValue, ToolCall

__all__ = ["Defense", "NoDefense"]


@runtime_checkable
class Defense(Protocol):
    """A pluggable defense applied around LLM and tool interactions (SPEC §19).

    Hooks are called at four points: before the LLM sees its input, after each
    tool returns output, before each tool call is executed, and on the final
    reply. The default pass-through behaviour is D0 (:class:`NoDefense`).
    """

    name: str

    def on_llm_input(self, messages: list[Message], ctx: RunContext) -> list[Message]: ...

    def on_tool_output(self, tool: str, output: TaggedValue, ctx: RunContext) -> TaggedValue: ...

    def on_tool_call(self, call: ToolCall, ctx: RunContext) -> Decision: ...

    def on_final(self, reply: str, ctx: RunContext) -> str: ...


class NoDefense:
    """D0: raw tool outputs into context, every call allowed (SPEC §9)."""

    name = "D0"

    def on_llm_input(self, messages: list[Message], ctx: RunContext) -> list[Message]:
        return messages

    def on_tool_output(self, tool: str, output: TaggedValue, ctx: RunContext) -> TaggedValue:
        return output

    def on_tool_call(self, call: ToolCall, ctx: RunContext) -> Decision:
        return Allow()

    def on_final(self, reply: str, ctx: RunContext) -> str:
        return reply
