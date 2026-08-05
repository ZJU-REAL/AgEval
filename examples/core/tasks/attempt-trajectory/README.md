# attempt-trajectory

Mechanism package for **per-invocation trajectory** (§8.9) and `Result.logs`.

Default mode runs two parent-bound Codex invokes; independent evaluator checks the
business answer (`answer == 42`) only. Trajectory / logs are recorded by Core and
must **not** be used as a scoring input or a substitute for PASS.

Optional `parameters.trajectory_mode` (`success` | `crash` | `timeout` | `cancel`)
probes partial evidence when the second invoke fails — evaluator still must not
invent PASS from incomplete trajectory.

## What you learn

- Multi-invoke path produces exportable attempt logs (`Result.logs` locator)
- Trajectory presence ≠ PASS
- Partial failure leaves honest evidence without rewriting evaluation truth

## Requirements

- Codex (or configured executor) for profile `codex-mini`

## Run

```bash
uv run bora lock examples/core --task attempt-trajectory
uv run bora run  examples/core --task attempt-trajectory
```

After a successful run, inspect the logs locator printed in the Result for the
trajectory tree.
