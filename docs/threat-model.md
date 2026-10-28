# Threat model

The full threat model is in [`../SPEC.md`](../SPEC.md) §8. This page is a pointer
and will be expanded alongside the attack catalog and defenses (**milestone M5+**).

## Summary

- **Assets:** customer funds (ledger balances), payee lists, consents/tokens,
  PII, ops privileges, audit integrity, system prompts.
- **Trust boundaries:** user ↔ agent; agent ↔ LLM; agent ↔ tools (MCP); PSP ↔
  bank (FDX/FAPI); bank ↔ switch (ISO 20022/mTLS); agent ↔ agent (A2A). All
  externally sourced free text is **untrusted** data.
- **Adversaries (A1–A7):** external injector, counterparty, malicious merchant,
  rogue/compromised PSP, malicious MCP server, malicious user/insider, colluding
  agents.
- **Injection channels (C1–C12):** email, documents, party names, ISO
  remittance/status text, statement entries, FDX responses, RAG/KB docs, MCP
  descriptors/results, A2A messages, direct prompts, Unicode tricks.
- **Attacker goals (G1–G9):** unauthorized transfer, payee tampering, consent
  abuse, data exfiltration, ops abuse, audit evasion, limit evasion, prompt/secret
  leakage, reconciliation fraud.

Defenses are catalogued in SPEC §9 (D0–D10). Oracles evaluate **post-run system
state**, not model text, which is the core measurement contribution (SPEC §10–§11).
