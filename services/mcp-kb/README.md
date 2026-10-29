# services/mcp-kb

MCP tool server exposing the RAG knowledge-base search tool (bank-c member help), indexed in pgvector; returns untrusted text.

Defined in SPEC §5.5 (also §3.1, §16). Implemented in **M4** as `search_kb`, which returns the help snippet as untrusted text. The pgvector index is the compose deployment of the same tool.
