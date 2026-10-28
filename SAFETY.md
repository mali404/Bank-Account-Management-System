# Safety and ethics

This document restates the safety posture of the AgentBank-Sec Testbed (SPEC §17).

## Simulation only

- **No real money, real banks, real ISO 20022 networks, real FDX endpoints, or
  real customer data.** There is no connector to FedNow, RTP, RTR, or any
  production API. Everything — banks, PSPs, the SimNow switch, customers,
  invoices, statements — is synthetic.
- Routing numbers use the reserved fictitious range `9999000xx` and are **not**
  real ABA numbers. E-mail addresses use `.test` domains (RFC 2606). Names and
  account numbers are generated and fictional.

## Network isolation

- Default network isolation: **no internet egress** from the simulation. The
  compose networks `bank-net`, `switch-net`, and `agent-net` are `internal`.
- The only possible outbound path is an **optional** LLM-API egress from the
  agent gateway, attached to the `egress` network and enabled only when
  `ALLOW_LLM_EGRESS=1`. It is **off by default**.

## Intended use and responsible disclosure

- Attack payloads in this repository target **this testbed only**. They exist to
  measure prompt-injection and agent-security defenses under ground-truth
  oracles.
- If a payload or technique developed here is found to transfer to a real
  product or service, **report it to the affected vendor before publication**,
  following coordinated/responsible-disclosure norms.
- When red-teaming **hosted** models, follow the model provider's usage
  policies. Record the provider and model for every run.

## Human-subjects note

- `user-sim` simulates customers approving or rejecting human-in-the-loop
  prompts. If you run studies with **real people** approving actions, that is
  human-subjects research and needs IRB/ethics approval — out of scope for this
  code.

## Specifications and data

- Do not redistribute member-only FDX specifications or MyStandards usage
  guides. This testbed implements its own **FDX-inspired** schemas (SPEC §1.1)
  and ships only freely downloadable ISO 20022 XSDs, subject to their terms.
