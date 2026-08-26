---
name: ageval-cli
description: >
  Operate ageval CLI (lock/run/plugin/view/publish/release/executors/campaign/evidence/status/cancel/jobs/results):
  flags, --set pointers, exit codes, --probe, offline fail-closed (AGEVAL_OFFLINE_AGENT),
  ACP entry readiness, plugin install, suite upload. Use when running ageval lock/run, PASS/FAIL/ERROR,
  trajectory export, Hub upload. Do not invent flags.
---

# ageval CLI

```bash
uv sync --frozen --all-packages
uv run ageval --help
```

Public commands: `ageval lock` `ageval run` `ageval campaign` `tasks` `jobs` `view` `plugin` `evidence` `ageval status` `ageval cancel` `executors` `publish` `release` `login` `agent` `registry` `cache` `results`. No `submit`. Path arguments are **dataset** roots.

```bash
uv run ageval lock examples/core --task config-minimal
uv run ageval run  examples/core --task acp-local-min
uv run ageval run  examples/core --task acp-docker-min --profiles examples/core/profiles.docker.yaml
uv run ageval run  examples/journeys --task terminal-jsonl-agg
uv run ageval run  official/demo@0.1.0 --dir tmp
uv run ageval run  … --probe          # lock + preflight, no Agent
uv run ageval executors -v
uv run ageval plugin install plugins/nooa
```

`--profiles` replaces the dataset job document. `--agent` and `--profiles` are mutually exclusive. `--set` allowlist: `/parameters/seed`, `/parameters/active_profile`, `/bindings/<role>/{model,executor,api_key,base_url,options/<key>}`. Not `limits.*`.

`ageval run` on a TTY prints a short recap; `--json` or a pipe keeps the result document.

Exit: 0 PASS / probe ready; 1 FAIL / probe not ready; 2 ERROR.

Single Attempt evidence: `<dataset>/.ageval/runs/<id>/` (`lock.json`, `result.json`, `trajectory.jsonl`). Trajectory ≠ PASS.

`--probe` missing `E2B_API_KEY` or ssh locator → ready false, started false.

Offline: `AGEVAL_OFFLINE_AGENT=1` must not PASS agent tasks.

Hub Leaderboard needs suite upload (`ageval results upload-suite`), not a lone `results upload`.

Flags: `uv run ageval <cmd> --help`. Source: `src/ageval/cli/main.py`.

Detail: [references/commands.md](references/commands.md), [references/failures.md](references/failures.md).
