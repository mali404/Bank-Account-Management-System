"""SQLAlchemy Core tables for one bank schema (SPEC §5.1).

The same metadata is created in each bank's SQLite file in tests and, with a
``schema_translate_map``, in the ``bank_a`` / ``bank_b`` / ``bank_c`` Postgres
schemas. Internal accounts (settlement, suspense, house) use a null customer.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, Text

metadata = MetaData()

customers = Table(
    "customers",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(140), nullable=False),
    Column("email", String(254), nullable=False),
    Column("phone", String(32), nullable=False, default=""),
    Column("risk_tier", String(16), nullable=False, default="standard"),
    Column("notes", String(2000), nullable=False, default=""),
)

accounts = Table(
    "accounts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("customer_id", String(64), ForeignKey("customers.id"), nullable=True),
    Column("type", String(16), nullable=False),
    Column("number", String(34), nullable=False, unique=True),
    Column("routing", String(9), nullable=False),
    Column("currency", String(3), nullable=False, default="USD"),
    Column("status", String(16), nullable=False, default="OPEN"),
)

ledger_entries = Table(
    "ledger_entries",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("txn_id", String(64), nullable=False, index=True),
    Column("account_id", String(64), ForeignKey("accounts.id"), nullable=False, index=True),
    Column("direction", String(8), nullable=False),
    Column("amount_minor", Integer, nullable=False),
    Column("ts", String(40), nullable=False),
)

transactions = Table(
    "transactions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("account_id", String(64), ForeignKey("accounts.id"), nullable=False, index=True),
    Column("amount_minor", Integer, nullable=False),
    Column("direction", String(8), nullable=False),
    Column("description", String(500), nullable=False, default=""),
    Column("counterparty_name", String(140), nullable=False, default=""),
    Column("remittance_info", String(2000), nullable=False, default=""),
    Column("iso_msg_id", String(35), nullable=True),
    Column("status", String(16), nullable=False, default="BOOK"),
)

payees = Table(
    "payees",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("customer_id", String(64), ForeignKey("customers.id"), nullable=False),
    Column("name", String(140), nullable=False),
    Column("account_number", String(34), nullable=False),
    Column("routing", String(9), nullable=False),
    Column("created_by", String(16), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("verified", Integer, nullable=False, default=0),
)

payments = Table(
    "payments",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("e2e_id", String(35), nullable=False),
    Column("uetr", String(36), nullable=False),
    Column("debtor_acct", String(64), nullable=False),
    Column("creditor_name", String(140), nullable=False),
    Column("creditor_acct", String(34), nullable=False),
    Column("creditor_routing", String(9), nullable=False),
    Column("amount_minor", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("initiated_by_principal", String(254), nullable=False, default=""),
    Column("initiated_via", String(16), nullable=False, default="app"),
    Column("consent_id", String(64), nullable=True),
    Column("agent_run_id", String(64), nullable=True),
    Column("iso_msg_id", String(35), nullable=True),
    Column("idempotency_key", String(80), nullable=True, unique=True),
    Column("direction", String(8), nullable=False, default="out"),
    Column("created_on", String(10), nullable=False, default=""),
)

consents = Table(
    "consents",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("client_id", String(64), nullable=False),
    Column("sub", String(254), nullable=False),
    Column("scopes", String(500), nullable=False),
    Column("status", String(32), nullable=False),
    Column("limits_json", String(2000), nullable=False, default="{}"),
    Column("payees_json", String(2000), nullable=False, default="[]"),
    Column("expires_at", String(40), nullable=False),
    Column("revoked_at", String(40), nullable=True),
)

hitl_requests = Table(
    "hitl_requests",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("customer_id", String(64), nullable=False),
    Column("payload", String(4000), nullable=False),
    Column("status", String(16), nullable=False),
)

cases = Table(
    "cases",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("status", String(16), nullable=False),
    Column("summary", String(2000), nullable=False, default=""),
)

kb_docs = Table(
    "kb_docs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("title", String(200), nullable=False),
    Column("body", Text, nullable=False),
)

documents = Table(
    "documents",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("customer_id", String(64), nullable=True),
    Column("name", String(200), nullable=False),
    Column("body", Text, nullable=False),
    Column("hidden", Text, nullable=False, default=""),
)

audit_outbox = Table(
    "audit_outbox",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String(40), nullable=False),
    Column("action", String(64), nullable=False),
    Column("detail", String(4000), nullable=False, default=""),
)

rfps = Table(
    "rfps",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("end_to_end_id", String(35), nullable=False, unique=True),
    Column("amount_minor", Integer, nullable=False),
    Column("creditor_name", String(140), nullable=False),
    Column("creditor_routing", String(9), nullable=False),
    Column("debtor_name", String(140), nullable=False),
    Column("remittance", String(2000), nullable=False, default=""),
    Column("status", String(16), nullable=False),
)

# Well-known internal account ids. They are not customer deposit accounts.
SETTLEMENT = "settlement"
SUSPENSE = "suspense"
HOUSE = "house"
