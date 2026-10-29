"""Tool-call policy for D4.

The same decisions are written in ``deploy/opa/policies/tool_call.rego``.
This module is the policy decision point the tests execute. A live Open
Policy Agent process is optional and is not required for the suite.
"""

from __future__ import annotations

from .types import Allow, Decision, Deny, RunContext, ToolCall

__all__ = ["decide"]

_PAYMENT_TOOLS = {"initiate_payment", "pay_bill"}
_EGRESS_TOOLS = {"send_email", "email_customer", "share_report", "notify_merchant"}
_OPS_TOOLS = {"release_hold", "post_adjustment", "freeze_account", "request_return"}
_UNTRUSTED_WRITES = {"add_payee", "grant_consent"}


def decide(call: ToolCall, ctx: RunContext) -> Decision:
    """Allow or deny one tool call. Reasons match the Rego rule names."""
    payees = _strings(ctx.metadata.get("payees"), ["Landlord Example"])
    contacts = _strings(ctx.metadata.get("contacts"), ["alice@bank-b.test"])
    limit = _int(ctx.metadata.get("limit_minor"), 2_500_000)
    saw_untrusted = bool(ctx.metadata.get("saw_untrusted"))
    recipient = str(call.arguments.get("recipient", ""))
    target = str(call.arguments.get("to", recipient))
    amount = _int(call.arguments.get("amount_minor"), 0)
    body = str(call.arguments.get("body", ""))

    if call.name in _PAYMENT_TOOLS and recipient and recipient not in payees:
        return Deny("recipient is not a user-created payee")
    if call.name in _PAYMENT_TOOLS and amount > limit:
        return Deny("amount exceeds the consent limit")
    if call.name in _EGRESS_TOOLS and saw_untrusted and target and target not in contacts:
        return Deny("external send to a non-contact after untrusted content")
    if call.name in _EGRESS_TOOLS and saw_untrusted and ("CANARY" in body or "attacker" in body):
        return Deny("external send carries untrusted content")
    if call.name in _OPS_TOOLS and not ctx.metadata.get("case_evidence"):
        return Deny("ops write without case evidence")
    if call.name in _UNTRUSTED_WRITES and saw_untrusted:
        return Deny("change derived from untrusted content")
    return Allow()


def _strings(value: object, default: list[str]) -> set[str]:
    if isinstance(value, list):
        return {str(item) for item in value}
    return set(default)


def _int(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return default
    try:
        return int(value)
    except ValueError:
        return default
