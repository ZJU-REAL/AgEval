# provider-l1-projection-denied

L1 probe for **credential / network projection denial** (`task_id: projection-denied`).

Asserts that host secrets, unrestricted network, or other non-projected
capabilities are **not** available inside the Attempt. Orchestrator-side L1
checks own the probe; package harness is a stub that must not be treated as a
success path outside the L1 runner.

## What you learn

- Scoped projection only — no host credential dump into the container
- Network / secret policy is Provider-enforced before effects

## Requirements

- Docker L1 path driven by Core’s L1 orchestrator

## Run

```bash
uv run bora lock examples/l1/provider-l1-projection-denied --task projection-denied
uv run bora run  examples/l1/provider-l1-projection-denied --task projection-denied
```

Use `--task projection-denied` (package `task_id`), not the directory name alone
if they differ in tooling.
