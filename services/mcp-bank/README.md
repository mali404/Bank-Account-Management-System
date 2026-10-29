# services/mcp-bank

MCP tool server exposing bank customer/app tools to agents (accounts, transactions, payees, transfers, inbox, documents, KB).

Defined in SPEC §5.5 (also §7). Implemented in **M4** as the `mcp-bank` tools in `agentbank_gateway.tools`. `inventory.yaml` pins each description hash. Calls go through the gateway, which records `run_id`.
