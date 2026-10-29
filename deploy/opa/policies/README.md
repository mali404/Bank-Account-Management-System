# OPA tool-call policies (Rego)

The Open Policy Agent policies that back defense **D4** (tool-call policy filter)
and control **AC-24** (access-control decisions made outside the LLM) live here
as `*.rego` files.

`tool_call.rego` is the D4 policy (SPEC §9, §12 AC-3/AC-24). The suite
evaluates the same rules in `agentbank_gateway.policy.decide`, so a running
OPA process is optional. `deploy/compose.yaml` does not start OPA.
