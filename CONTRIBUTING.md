# Contributing

Thanks for your interest in the AgentBank-Sec Testbed. This is simulated
research software (see [`SAFETY.md`](SAFETY.md)).

## Development setup

Prerequisites: [uv](https://docs.astral.sh/uv/), GNU make, and (for the compose
stack) Docker Engine + Compose v2. uv manages the Python 3.12 toolchain itself.

```sh
make bootstrap        # or: uv sync --all-packages
```

## Workflow

Before opening a pull request, make sure the checks pass:

```sh
uv sync --all-packages
make lint        # ruff check + ruff format --check
make typecheck   # mypy (strict)
make test        # pytest (unit; no docker/network)
```

`make check` runs all three. If you touched the compose stack, also run
`make compose-config` and, with docker available, `make up && make test-compose`.

### Code style

- Python 3.12, fully typed (mypy strict). Keep modules small and focused.
- Formatting and imports are handled by `ruff format` and `ruff check --fix`
  (line length 100). Run `make format`.
- New code gets tests. Unit tests live in `tests/unit/` (and alongside each lib);
  mark tests needing the stack with `@pytest.mark.compose`.

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/) for messages,
  e.g. `feat(iso): add pacs.008 builder`, `fix(switch): reject duplicate UETR`,
  `docs: clarify bootstrap`.
- Keep PRs focused; reference the milestone (M0–M8) and relevant SPEC section.
- There is **no CLA and no DCO sign-off requirement** — contributions are
  accepted under the project's Apache-2.0 license by submitting them.

## Safety

Keep the simulation offline by default. Never commit secrets, real credentials,
real customer data, or member-gated FDX/MyStandards material. Attack content
must target this testbed only; follow the responsible-disclosure guidance in
[`SAFETY.md`](SAFETY.md).
