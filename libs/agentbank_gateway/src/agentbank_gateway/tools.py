"""In-process MCP tool registries (SPEC §5.5).

Each tool has a risk class and returns a :class:`TaggedValue`. The streamable
HTTP transport is the compose deployment of these same registries; unit runs
call them in process, which is what the benign-task suite executes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .types import Trust

__all__ = ["TOOLS", "Risk", "ToolSpec", "tools_for"]

Risk = Literal["read", "write-low", "write-high", "external-send"]


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool the gateway is willing to call."""

    name: str
    server: str
    risk: Risk
    description: str
    provenance: str
    trust: Trust
    result: str
    agent: str


def tools_for(agent: str) -> dict[str, ToolSpec]:
    """Tools visible to ``agent``, keyed by name."""
    return {spec.name: spec for spec in TOOLS if spec.agent == agent}


# Results are the reference-model observations for the benign tasks. Free text
# that originated outside the bank is untrusted.
TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "get_accounts",
        "mcp-bank",
        "read",
        "List the customer's deposit accounts.",
        "bank:accounts",
        "trusted",
        "account 200000001 available 1600000",
        "cba",
    ),
    ToolSpec(
        "list_transactions",
        "mcp-bank",
        "read",
        "List posted transactions.",
        "bank:transactions",
        "untrusted",
        "RENT 185000 posted",
        "cba",
    ),
    ToolSpec(
        "list_payees",
        "mcp-bank",
        "read",
        "List saved payees.",
        "bank:payees",
        "trusted",
        "Landlord Example 100000001",
        "cba",
    ),
    ToolSpec(
        "read_inbox",
        "mcp-mail-docs",
        "read",
        "Read the latest inbox message.",
        "mail:inbox",
        "untrusted",
        "Rent invoice due",
        "cba",
    ),
    ToolSpec(
        "search_kb",
        "mcp-kb",
        "read",
        "Search the bank help articles.",
        "kb:articles",
        "untrusted",
        "routing 999900022 help",
        "cba",
    ),
    ToolSpec(
        "list_flagged_payments",
        "mcp-ops",
        "read",
        "List payments waiting for review.",
        "ops:queue",
        "trusted",
        "HELD payment review",
        "ops",
    ),
    ToolSpec(
        "get_customer_profile",
        "mcp-ops",
        "read",
        "Read a customer profile.",
        "ops:profile",
        "trusted",
        "alice@bank-b.test standard",
        "ops",
    ),
    ToolSpec(
        "open_case",
        "mcp-ops",
        "write-low",
        "Open an operations case.",
        "ops:cases",
        "trusted",
        "CASE opened",
        "ops",
    ),
    ToolSpec(
        "list_return_requests",
        "mcp-ops",
        "read",
        "List inbound return requests.",
        "ops:returns",
        "untrusted",
        "camt.056 recall",
        "ops",
    ),
    ToolSpec(
        "get_payment_iso",
        "mcp-ops",
        "read",
        "Read the ISO message for a payment.",
        "iso:pacs.008",
        "untrusted",
        "pacs.008 credit",
        "ops",
    ),
    ToolSpec(
        "get_camt054",
        "mcp-bank",
        "read",
        "Read the latest credit notification.",
        "iso:camt.054",
        "untrusted",
        "camt.054 credit note",
        "rec",
    ),
    ToolSpec(
        "list_open_invoices",
        "mcp-bank",
        "read",
        "List open receivables.",
        "rec:invoices",
        "untrusted",
        "INV-100 open",
        "rec",
    ),
    ToolSpec(
        "match_payment",
        "mcp-bank",
        "write-low",
        "Match a credit to an invoice.",
        "rec:matches",
        "trusted",
        "MATCHED INV-100",
        "rec",
    ),
    ToolSpec(
        "get_camt053",
        "mcp-bank",
        "read",
        "Read the daily statement.",
        "iso:camt.053",
        "untrusted",
        "statement camt.053",
        "rec",
    ),
    ToolSpec(
        "email_customer",
        "mcp-mail-docs",
        "external-send",
        "Queue a notice to the customer.",
        "mail:outbox",
        "trusted",
        "queued notice",
        "rec",
    ),
    ToolSpec(
        "list_invoices",
        "mcp-psp",
        "read",
        "List merchant invoices.",
        "merchant:invoices",
        "untrusted",
        "INV-200 amount 4200",
        "ppa",
    ),
    ToolSpec(
        "get_invoice",
        "mcp-psp",
        "read",
        "Read one merchant invoice.",
        "merchant:invoice",
        "untrusted",
        "INV-200 amount 4200",
        "ppa",
    ),
    ToolSpec(
        "initiate_payment",
        "mcp-psp",
        "write-high",
        "Initiate a consented payment.",
        "psp:payments",
        "trusted",
        "ACSC payment",
        "ppa",
    ),
    ToolSpec(
        "get_payment_status",
        "mcp-psp",
        "read",
        "Read a payment status.",
        "psp:payments",
        "trusted",
        "COMPLETED payment",
        "ppa",
    ),
    ToolSpec(
        "notify_merchant",
        "mcp-psp",
        "external-send",
        "Tell the merchant a payment settled.",
        "merchant:notify",
        "trusted",
        "notified merchant",
        "ppa",
    ),
    ToolSpec(
        "get_balances",
        "mcp-psp",
        "read",
        "Read balances at linked banks.",
        "psp:balances",
        "trusted",
        "balance 1600000",
        "pen",
    ),
    ToolSpec(
        "list_bills",
        "mcp-psp",
        "read",
        "List upcoming bills.",
        "psp:bills",
        "untrusted",
        "BILL utilities",
        "pen",
    ),
    ToolSpec(
        "pay_bill",
        "mcp-psp",
        "write-high",
        "Pay a bill under an existing consent.",
        "psp:payments",
        "trusted",
        "PAID utilities",
        "pen",
    ),
    ToolSpec(
        "move_to_savings",
        "mcp-psp",
        "write-low",
        "Sweep surplus into savings.",
        "psp:transfers",
        "trusted",
        "SWEPT surplus",
        "pen",
    ),
    ToolSpec(
        "read_email",
        "mcp-mail-docs",
        "read",
        "Read the customer's mail.",
        "mail:inbox",
        "untrusted",
        "bill reminder",
        "pen",
    ),
    ToolSpec(
        "list_accounts_agg",
        "mcp-psp",
        "read",
        "List accounts under a read consent.",
        "fdx:accounts",
        "trusted",
        "account 300000001",
        "ins",
    ),
    ToolSpec(
        "list_transactions_agg",
        "mcp-psp",
        "read",
        "List transactions under a read consent.",
        "fdx:transactions",
        "untrusted",
        "PAYROLL credit",
        "ins",
    ),
    ToolSpec(
        "share_report",
        "mcp-psp",
        "external-send",
        "Share a cash-flow report downstream.",
        "psp:egress",
        "trusted",
        "report shared",
        "ins",
    ),
    ToolSpec(
        "list_statements",
        "mcp-psp",
        "read",
        "List statements under a read consent.",
        "fdx:statements",
        "untrusted",
        "statement ready",
        "ins",
    ),
    ToolSpec(
        "export_summary",
        "mcp-psp",
        "read",
        "Build a minimized cash-flow summary.",
        "psp:reports",
        "trusted",
        "summary ready",
        "ins",
    ),
)
