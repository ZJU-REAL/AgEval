# CLI failure diagnosis

| Symptom | Check |
| --- | --- |
| exit 2, empty stdout on lock | Config error on stderr (`unknown_profile`, schema, etc.) |
| lock `unsupported_capability` / `unsupported executor` | Kind not in `bora executors` `.supported` — coding agents need `executor: Official/acp` |
| lock `options.entry required` | ACP profile missing `options.entry` |
| Agent ERROR offline | Expected under `BORA_OFFLINE_AGENT=1` |
| `l1_executor_unbound` | L1 invoke has no SPI ``bind_to_target`` (or placement resolver missing) |
| `image_contribute_unsatisfied` | Bound external executor but bake chain empty / no `Dockerfile.bake` — `$bora-plugin` |
| `nooa_package_missing` / `No module named 'nooa'` | Host SPI needs `uv sync --extra nooa`; L1 bake installs it in the image |
| ACP entry not ready | `bora executors -v` → that `entry_id` `host_ready` / install pin; no invoke-time `npm i` |
| PASS without real model | Forbidden — do not use fixtures as public proof |
| Trajectory empty | Non-empty `agent_profiles` + harness `Agent.session`/`invoke`. Plugin L1 with no tools: worker import / collect — `$bora-plugin` |
| Resume skipped an ERROR | `--resume-suite` skips finished `(task_id, attempt_index)` including ERROR. New suite to retry. |
| Export fails `unsealed_invocation` | Attempt still running or metadata not terminal |
| Export fails `secret_residual` | Fix source evidence; do not strip secrets by hand in export dir |
| Docker L1 ERROR | Docker daemon, image build, network/creds projection; read `l1.json` / agent meta under logs |

Design: `docs/design/05-runtime/evidence.md`, `docs/design/07-budget-evaluation-failure.md`.
