# tau3-airline (BORA Dataset)

Port of **τ³-bench / tau2-bench** `airline` domain onto BORA outer lifecycle.

| Field | Value |
| --- | --- |
| Upstream | https://github.com/sierra-research/tau2-bench @ `v1.0.1` |
| Domain | airline (50 tasks, base split) |
| Agents | `user` + `service` via `profiles.yaml` → `grok-build` |
| Bridge | BORA Agent ACP ↔ tau2 `Environment` tools + `evaluate_simulation` |
| Shared | Dataset-level `shared/lib` + `shared/assets` |

## Layout

```text
bora.yaml / profiles.yaml
shared/
  lib/          # harness_core, bridge, evaluator_core (PYTHONPATH)
  assets/       # db.json, policy.md, tasks.json (in packageDigest)
tasks/airline-NN/
  task.yaml / harness.py / evaluator.py
  data/         # agent-visible scenario + policy copy
  evaluation/   # gold / full task JSON (evaluator-only)
```

No per-task `lib/` copies — modules live once under `shared/lib`.

## Run

```bash
uv run bora lock examples/tau3-airline --task airline-00
uv run bora run  examples/tau3-airline --task airline-00
uv run bora run  examples/tau3-airline   # full suite
uv run python scripts/check_shared_lib_collisions.py examples/tau3-airline
```

Host needs `tau2==1.0.1` (see `requirements.txt`) for tools/DB scoring.

## Evidence notes

- Attempt PASS only from independent evaluator (tau2 ENV+COMMUNICATE product).
- `HarnessTerminal.completed` ≠ PASS.
- Gold lives under each task's `evaluation/` (not under `shared/`).
- Presence of this package / Hub Shared UI does **not** raise evidence grade.

## Generate / expand members

```bash
python examples/tau3-airline/scripts/generate_package.py --ids 0,1,2,3,4
python examples/tau3-airline/scripts/generate_package.py --all
```
