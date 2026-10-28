# bankbench

The evaluation harness: scenario runner, ground-truth oracles, metrics, and
report/parquet output (SPEC §10–§11, §19). `adapters/` integrate AgentDojo,
garak, PyRIT, promptfoo, and Inspect. Populated in **milestone M5** (framework
adapters land in **M7**). The stable results-row schema lives in
`agentbank_common.results_schema`.
