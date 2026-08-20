---
name: ageval-platform
description: >
  ageval platform map: authority (docs/design vs ARCHITECTURE vs Issues), Core vs
  dataset ownership, red lines (trajectory≠PASS, no secrets, mechanism-named
  adapters), evidence grades, which sibling skill to load. Use when entering the
  repo, asking "what is ageval", "who owns PASS", "read order", or "evidence grade".
  Not a substitute for docs/design.
---

# ageval platform

Runtime owns lock, Attempt, the box, hard ceilings, trajectory, independent evaluation. The dataset owns the business loop in `run.py`.

## Read order

1. `docs/design/` — product + mechanism (self-contained; no external BRIEF)
2. `ARCHITECTURE.md` — modules
3. GitHub Issues — delivery
4. Code / tests / examples — what is shipped

`website/` is reader-facing. Conflict → fix `docs/` first.

## Ownership

| Owns | Does not own |
| --- | --- |
| **Core:** lock, Attempt phases, box Protocol, Agent Service, hard ceilings, bind PASS | Task loop, scoring algorithm |
| **`run.py`:** loop, tools, publish | PASS, credentials, opening the box |
| **evaluator:** truth | Starting the Agent |

## Red lines

1. Trajectory ≠ PASS.
2. No secrets in lock / yaml / evidence. Env vars are locators.
3. Adapters named by mechanism (`acp`, `docker`, `e2b`, `ssh`). Never by benchmark.
4. Kind is `environment: local|docker|e2b|ssh`.
5. Unknown format → one error.
6. Coding agents: `executor: acp` + `options.entry`. Not `executor: pi`.
7. Plugins: exclusive / chain slots only. `ageval plugin install` never rewrites profiles.
8. Do not claim `isolated` / `real-benchmark-verified` from one happy path.

## Skills

| Task | Load |
| --- | --- |
| CLI | `$ageval-cli` |
| `ageval.yaml` / task layout | `$ageval-config-package` |
| `run.py` / AgentSession | `$ageval-sdk-harness` |
| `ageval.plugin/1` | `$ageval-plugin` |

Detail: [references/authority.md](references/authority.md), [references/red-lines.md](references/red-lines.md), [references/shipped-surfaces.md](references/shipped-surfaces.md).
