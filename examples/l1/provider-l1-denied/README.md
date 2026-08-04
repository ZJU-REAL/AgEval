# provider-l1-denied

L1 **hidden-material denial** probe (`task_id: hidden-material-denied`).

Harness deliberately searches for `evaluation/gold.json` inside the Attempt
workspace. Success for this package means the gold path is **not** visible
(fail-closed view). Seeing gold is a security regression even if the harness
“completes”.

## What you learn

- Evaluator-only material stays off the harness mount
- Negative isolation probes are part of the public L1 surface

## Requirements

- Docker L1 path

## Run

```bash
uv run bora lock examples/l1/provider-l1-denied --task hidden-material-denied
uv run bora run  examples/l1/provider-l1-denied --task hidden-material-denied
```

Note: directory name is `provider-l1-denied`; **task_id** in `bora.yaml` is
`hidden-material-denied` — pass that id to `--task`.
