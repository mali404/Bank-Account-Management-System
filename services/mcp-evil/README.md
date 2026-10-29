# services/mcp-evil

A **deliberately malicious** MCP tool server used for supply-chain / tool-poisoning
scenarios (descriptor poisoning, rug-pull). It ships poisoned tool descriptors and
rogue tools on purpose.

It is **only** enabled under the `attacks` docker compose profile in later
milestones; it is never part of the default stack.

Defined in SPEC §5.5 (also §10 scenarios S13/S14). Implemented in **M5**.
