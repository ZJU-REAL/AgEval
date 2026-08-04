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

| Command | Use for |
| --- | --- |
| `bora executors` | Supported `executor:` kinds + host readiness; ACP entry probe (JSON) |
| `bora executors -v` | Same + tools/session + default credential env *names* + entry detail |
| `bora lock <package> --task <id>` | Config lock summary (no Agent) |
| `bora lock ... --set /parameters/seed=7` | Allowlisted override |
| `bora run <package> --task <id>` | One foreground Attempt |
| `bora run ... --set '/parameters/active_profile="pi-acp"'` | Profile switch (allowlisted) |
| `bora campaign <package> --task <id> --matrix ...` | Serial parameter matrix (partial) |
| `bora evidence <logs-path> --out <dir>` | Sealed trajectory export (no score change) |
| `bora submit` / `bora status` / `bora cancel` | Durable control sketch (v0.12) |

Discover flags with `uv run bora <cmd> --help`. Source of truth: `src/bora/cli/main.py`.

### Which `executor:` / ACP `entry` values?

```bash
uv run bora executors
# .supported     = agent_profiles[].executor values (e.g. acp, openai-http)
# .acp_entries   = options.entry ids + engine/acp binary readiness
# .host_ready    = kinds that can actually run here
# .missing_binary = (legacy CLI kinds only; ACP uses per-entry readiness)
```

Coding-agent packages use:

```yaml
executor: acp
options:
  entry: opencode   # or codex | claude-code | pi | grok-build | …
```

Do **not** hardcode a fixed list; inventory is authoritative. Do **not** use
`executor: codex|pi|opencode|claude-code` (migrated to ACP entry).

## Allowlisted `--set` pointers

Only these (see Config Core):

- `/parameters/seed`
- `/parameters/active_profile`
- `/limits/wall_time_seconds`
- `/limits/agent_invocations`
- `/limits/environment_actions`
- `/limits/memory_mb`

Value after `=` is JSON (strings need quotes): `--set '/parameters/active_profile="opencode-acp"'`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | PASS |
| `1` | FAIL (evaluator) |
| `2` | ERROR / config / runtime |

## Interpret `bora run` JSON

Typical stdout fields: `status`, `score`, `assurance`, `agent_invocations`, `evidence_path`, **`logs`** (Attempt evidence root).

- Inspect trajectory: open `$logs/agent/invocations/<nnnn>-*/trajectory.jsonl` (**turn-level** training rows) and `events.jsonl` (optional stream/debug)
- Export: `uv run bora evidence "$logs" --out /tmp/bora-export`
- Trajectory presence **never** upgrades score

## Offline / fail-closed

```bash
BORA_OFFLINE_AGENT=1 uv run bora run examples/core/sdk-agent-session --task sdk-agent-session
```

Must not PASS agent packages. Typed errors only.

## Recommended smokes

| Goal | Command |
| --- | --- |
| List executors / ACP entries | `uv run bora executors` / `uv run bora executors -v` |
| Lock only | `uv run bora lock examples/core/config-minimal --task config-minimal` |
| ACP multi-turn (host) | `uv run bora run examples/core/acp-agent-conformance --task acp-agent-conformance` |
| ACP entry switch | `… --set '/parameters/active_profile="pi-acp"'` (or `opencode-acp` / `grok-build-acp` / …) |
| Trajectory | `uv run bora run examples/core/attempt-trajectory --task attempt-trajectory` |
| Hard ceiling | `uv run bora run examples/core/hard-ceiling-trajectory --task hard-ceiling-trajectory` |
| L1 ACP placement | `uv run bora run examples/l1/acp-agent-placement --task acp-agent-placement` |
| L1 visibility | `uv run bora run examples/l1/builtin-executor-visibility --task builtin-executor-visibility` |

## Detail

- Command semantics & Result fields: [references/commands.md](references/commands.md)
- Failure diagnosis: [references/failures.md](references/failures.md)
