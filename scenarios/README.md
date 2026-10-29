# Scenarios

One YAML file per attack in SPEC §10: `scenarios/S01.yaml` through
`scenarios/S24.yaml`.

Fields: `id`, `title`, `adversary`, `channel`, `target_agent`,
`user_task_id`, `injection_template`, `placement`, `goal`,
`success_oracle`, `utility_oracle`, `severity`, `tags`.

`user_task_id` points at a benign task in `tasks/`. `utility_oracle` is
`utility_met`. `success_oracle` is a name in `bankbench.oracles.ORACLES`.
`injection_template` is a file under `templates/injections/`.

The runner emits a benign twin for each file (same task, `injected` false)
and an injected run that renders the template with `goal` as `payload`.
