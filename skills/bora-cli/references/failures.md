# CLI failure diagnosis

| Symptom | Check |
| --- | --- |
| exit 2, empty stdout on lock | Config error on stderr (`unknown_profile`, schema, etc.) |
| Agent ERROR offline | Expected under `BORA_OFFLINE_AGENT=1` |
| PASS without real model | Forbidden — do not use fixtures as public proof |
| Trajectory empty | Session path requires `parameters.use_agent_session: true` + parent Agent Service |
| Export fails `unsealed_invocation` | Attempt still running or metadata not terminal |
| Export fails `secret_residual` | Fix source evidence; do not strip secrets by hand in export dir |
| Docker L1 ERROR | Docker daemon, image build, network policy; read `l1.json` under logs |

Design: `docs/design/05-runtime-core.md`, `docs/design/07-budget-evaluation-failure.md`.
