# Research Notes

This document collects the open questions this project surfaces that I would like to investigate during a PhD. Each note states the question, why it matters, what's already known, and a sketch of how I'd approach it.

## 1. Compositional auditability of role-based agent systems

**Question.** Given a multi-agent system with an explicit role hierarchy, can we automatically generate counterfactual traces — *"what would the agent have decided if the user had been a teller?"* — and use them to test whether policy decisions are role-monotonic?

**Why it matters.** Real banks audit not just what happened but what *would* have happened under the same evidence with different actors. If we can mechanize this, RBAC bugs become regression-detectable.

**State of the art.** LangGraph's checkpoints make state replay trivial, but role-counterfactuals require systematically substituting the role and *only* the role in a recorded trace, then re-deriving the trajectory. Closest prior art: counterfactual reasoning in causal inference + LLM trajectory replay (LangSmith, Inspect, Promptfoo).

**Sketch.** Build a harness that consumes a Jaeger trace, identifies all `role = X` settings in the state, substitutes each declared role, and re-runs the supervisor with everything else held constant. Compare tool calls, denials, and final responses pairwise. Surface any non-monotonic transitions (e.g., a role with strictly fewer permissions producing a result that a higher-privilege role would not).

## 2. Trust calibration in supervisor delegation

**Question.** When the supervisor must delegate across roles for cross-functional tasks (e.g., "open an account and immediately fund it from an existing one"), how should it weight the confidence of each role-agent's response?

**Why it matters.** Naive supervisors today either always defer or always re-check; both miss the right answer in the middle.

**Sketch.** Treat delegation as a multi-armed bandit where the arms are role-agent + tool-set combinations and the reward is post-hoc audit-compliance score. Train an offline policy on synthetic traces with known ground truth.

## 3. Adversarial robustness of natural-language banking instructions

**Question.** What is the minimum-effective prompt-injection defense, measured on a banking-instruction benchmark we'd construct?

**Why it matters.** "Defense in depth" claims in the literature rarely have shared benchmarks for regulated domains. The closest existing benchmark (e.g., AgentDojo) is general-purpose.

**Sketch.** Construct a dataset of (legitimate user message, injected payload, success criterion) triples covering the five role-perspectives in this system. Evaluate three layers — input filtering, structural separation (the trusted/untrusted segregation pattern), and output post-conditions — to measure marginal contribution of each.

## 4. Tool-call planning under uncertainty

**Question.** Would a planner-style architecture (LLM produces a DAG of intended tool calls and their dependencies, then executes) outperform reactive ReAct loops for compliance-heavy multi-step flows?

**Why it matters.** Compliance flows often have natural DAG structure (KYC → fraud screen → balance check → approval → settle). Reactive loops backtrack expensively when they violate ordering constraints.

**Sketch.** Implement a planner agent in the supervisor that emits a DAG conforming to a published schema; compare wall-clock latency, tool-call count, and policy-violation rate against the existing ReAct customer flow on a held-out scenario set.

## 5. Tamper-evident audit at scale

**Question.** Our HMAC chain is O(N) to verify and serializes all writes. What's the minimal-overhead structure that preserves tamper-evidence while supporting concurrent appends and sublinear verification?

**Why it matters.** Banks generate billions of audit events. Per-event chaining is fine for a course project; not for production.

**Sketch.** Compare three options: (a) Merkle-tree per-day with daily roots anchored externally, (b) certificate-transparency-style append-only log with inclusion proofs, (c) AWS QLDB-style verifiable digest. Trade-offs along read latency, write throughput, and operator overhead.

---

These items are deliberately scoped: each could be a workshop paper, a deeper conference paper, or a chapter in a thesis. The current implementation is the experimental platform on which I'd run them.
