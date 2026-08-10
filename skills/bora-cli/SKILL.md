---
name: bora-cli
description: >
  Operate BORA public CLI (bora lock/run/executors/campaign/evidence/status/submit/cancel):
  install with uv, command flags, allowlisted --set pointers, exit codes, Result.logs
  trajectory locator, offline fail-closed (BORA_OFFLINE_AGENT), list supported executor
  kinds and ACP entry readiness, and which example packages to run. Use when the agent
  must lock a package, run an Attempt, list agent_profiles.executor / options.entry values,
  export trajectory, interpret PASS/FAIL/ERROR, debug CLI output, or choose a public smoke.
  Trigger phrases: "bora run", "bora lock", "bora executors", "which executor", "ACP entry",
  "export trajectory", "Result.logs", "exit code", "offline agent", "switch profile".
  Do not invent flags not in production.
---

# BORA CLI

## Install

From repo root:

```bash
uv sync --frozen --all-packages
uv run bora --help
```

## Commands (shipped)

| Command                                                    | Use for                                                              |
| ---------------------------------------------------------- | -------------------------------------------------------------------- |
| `bora executors`                                           | Supported `executor:` kinds + host readiness; ACP entry probe (JSON) |
| `bora executors -v` / `--verbose`                          | Same + tools/session + default credential env _names_ + entry detail |
| `bora -V` / `bora --version`                               | Package version (`-V`; keep `-v` free for verbose) |
| `bora lock <package> --task <id>`                          | Config lock summary (no Agent); includes `job_overlay`               |
| `bora lock ... --set /parameters/seed=7`                   | Allowlisted override                                                 |
| `bora lock/run ... --profiles path/to/profiles.yaml`       | Alternate job binding file (replaces Database `profiles.yaml`)       |
| `bora run <package> --task <id>`                           | One foreground Attempt                                               |
| `bora run ... --set '/bindings/solver/options/entry="pi"'` | Job binding override (entry/model; #59)                              |
| `bora campaign <package> --task <id> --matrix ...`         | Serial matrix (`/parameters/*` or `/bindings/<role>/…`)               |
| `bora evidence <logs-path> --out <dir>`                    | Sealed trajectory export (no score change)                           |
| `bora results upload-suite …`                              | Suite aggregates → Registry (includes job_overlay when present)      |
| `bora results export-profiles <suite_run_id> --out …`      | Rehydrate job binding as profiles.yaml (#59; locators only)          |
| `bora submit` / `bora status` / `bora cancel`              | Durable control sketch (v0.12)                                       |

Discover flags with `uv run bora <cmd> --help`. Source of truth: `src/bora/cli/main.py`.

### Which `executor:` / ACP `entry` values?

```bash
uv run bora executors
uv run bora executors -v
# .supported     = agent_profiles[].executor values (e.g. acp, openai-http)
# .acp_entries   = options.entry ids + engine/acp binary readiness
# .host_ready    = kinds that can actually run here
# .missing_binary = (legacy CLI kinds only; ACP uses per-entry readiness)
# Note: package version is `bora -V` / `--version` (not `-v`).
```

Coding-agent packages use:

```yaml
executor: acp
options:
  entry: opencode # or codex | claude-code | pi | grok-build | …
```

Do **not** hardcode a fixed list; inventory is authoritative. Do **not** use
`executor: codex|pi|opencode|claude-code` (migrated to ACP entry).

## Allowlisted `--set` pointers

Fixed parameter leaves (see Config Core):

- `/parameters/seed`
- `/parameters/active_profile`

Job binding axes (#59):

- `/bindings/<role_id>/model`
- `/bindings/<role_id>/executor`
- `/bindings/<role_id>/api_key`
- `/bindings/<role_id>/base_url`
- `/bindings/<role_id>/options/entry`

**Not** overridable: intent `limits.*` (task contract).

Value after `=` is JSON (strings need quotes):  
`--set '/bindings/solver/options/entry="pi"'` · `--set '/parameters/active_profile="solver"'`.

## Exit codes

| Code | Meaning                  |
| ---- | ------------------------ |
| `0`  | PASS                     |
| `1`  | FAIL (evaluator)         |
| `2`  | ERROR / config / runtime |

## Interpret `bora run` JSON

Typical stdout fields: `status`, `score`, `assurance`, `agent_invocations`, `evidence_path`, **`logs`** (Attempt evidence root).

- Inspect trajectory: open `$logs/agent/invocations/<nnnn>-*/trajectory.jsonl` (**turn-level** training rows) and `events.jsonl` (optional stream/debug)
- Export: `uv run bora evidence "$logs" --out /tmp/bora-export`
- Trajectory presence **never** upgrades score

## Offline / fail-closed

```bash
BORA_OFFLINE_AGENT=1 uv run bora run examples/core --task sdk-agent-session
```

Must not PASS agent packages. Typed errors only.

## Recommended smokes

| Goal                         | Command                                                                                                                           |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| List executors / ACP entries | `uv run bora executors` / `uv run bora executors -v`                                                                              |
| Package version | `uv run bora -V` / `uv run bora --version` |
| Lock only                    | `uv run bora lock examples/core --task config-minimal`                                                                            |
| ACP multi-turn (host)        | `uv run bora run examples/core --task sdk-agent-session`                                                                          |
| ACP entry switch             | `uv run bora run examples/core --task builtin-executor-conformance --set '/bindings/solver/options/entry="pi"'`                   |
| Trajectory                   | `uv run bora run examples/core --task attempt-trajectory`                                                                         |
| Hard ceiling                 | `uv run bora run examples/core --task hard-ceiling-trajectory`                                                                    |
| L1 SDK session               | `uv run bora run examples/l1 --task sdk-session-single-actor`                                                                     |
| L1 isolation contracts       | Provider tests: `uv run pytest tests/provider_l1/test_harness_isolation_contracts.py tests/provider_l1/test_filtered_mount.py -q` |

## Detail

- Command semantics & Result fields: [references/commands.md](references/commands.md)
- Failure diagnosis: [references/failures.md](references/failures.md)
