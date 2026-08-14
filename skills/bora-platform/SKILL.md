---
name: bora-platform
description: >
  BORA (Bounded Orchestration for Runtime Agents) platform map for coding agents:
  authority order (docs/design vs ARCHITECTURE vs GitHub Issues), Core vs package
  ownership, red lines (trajectory≠PASS, no secrets in lock/evidence, mechanism-named
  adapters only), evidence grades, and which sibling skill to load next. Use when an
  agent enters the BORA repo, needs orientation before changing code/packages, asks
  "what is BORA", "who owns PASS", "read order", "evidence grade", "which skill",
  or which docs are authoritative. Not a substitute for docs/design; only routes
  and hard constraints.
---

# BORA platform

Runtime owns the boundary (lock, Attempt, isolation, capability, trajectory,
independent evaluation). The package owns the business loop.

## Read order (do not invent authority)

1. `docs/design/` — product + mechanism (primary)
2. `ARCHITECTURE.md` — module ownership / dependency direction
3. GitHub Issues — delivery tracking and acceptance
4. Code / tests / examples — evidence of what is shipped

`website/` is reader-facing only; conflict → fix `docs/` first.

Change the module tree in `ARCHITECTURE.md` first. Do not ship marker `LifecycleStages` (empty `cleanup`/`evaluate`/`bind` while production logic lives elsewhere). Do not ship empty Registry `*Service` shells that Handler never calls.

Conflict → stop; fix the highest authority artifact first, then sync downstream.

## Ownership split

| Owns | Does not own |
| --- | --- |
| **Core:** `load_and_lock`, Run/Trial/Attempt, Provider projection, Agent Service invoke+trajectory, hard ceilings, evaluator barrier, flat Result | Package business roles, scoring algorithms |
| **Package harness:** loop, roles, local Tools, handoff data, `ctx.params` | PASS/FAIL, credentials, isolation mounts |
| **Evaluator (package):** truth / score algorithm | Starting Agent, host secrets, rewriting runtime errors into PASS |

Authoring / porting / scenario-homogeneous Datasets: load `$bora-config-package`
(Hub Leaderboard comparability and suite `config_fingerprint` live there too).

## Red lines (fail closed)

1. **Trajectory ≠ PASS** — only independent evaluator may form PASS. Missing trajectory must not invent PASS.
2. **No secrets** in lock, package yaml, evidence, export, or examples. Env vars are locators only.
3. **Adapters** named by mechanism/protocol/resource (`acp`, `openai-http`, `postgresql`, docker; ACP **entries** `codex`/`pi`/…) — never Benchmark/task/domain names.
4. **Do not claim** suite-wide `isolated` or `real-benchmark-verified` from one happy path.
5. **Skills only describe shipped surfaces** — never invent CLI flags or Core APIs.
6. **Coding-agent Target:** `executor: Official/acp` + `options.entry` — not private CLI `executor: codex|pi|…`.
7. **Plugins:** fixed L0–L5 extension points + registry; `bora plugin install` never rewrites profiles; Recognition ≠ L1 Ready (`image_contribute` bake); no executor dual path.
8. **Hub Leaderboard / Task Jobs need suite uploads** — `bora results upload` (single Attempt) is not enough for primary Hub surfaces; use suite run + `bora results upload-suite` (often `--with-attempts`). Public Leaderboard further requires a **complete**, **release-bound** suite; incomplete or draft-bound rows stay on Jobs. Detail: `$bora-cli` § Hub visibility.

## Evidence grades (honest)

| Claim | Requires |
| --- | --- |
| `runnable-mvp` (L0) | Real public `bora run` + real Agent path (scoped journeys) |
| `assurance:l1` | Measured Docker combo only (see Result.l1 / execution_location) |
| `isolated` / `real-benchmark-verified` | Matching acceptance evidence — **not** inferred |

## Route to sibling skills

| Task | Load |
| --- | --- |
| Run CLI / interpret exit / export trajectory | `$bora-cli` |
| Write or review `bora.yaml` / package layout | `$bora-config-package` |
| Write harness / AgentSession / ToolSet | `$bora-sdk-harness` |
| Write or review `bora.plugin/1` | `$bora-plugin` |

## Progressive detail

- Authority & conflicts: [references/authority.md](references/authority.md)
- Red-line checklist with examples: [references/red-lines.md](references/red-lines.md)
- Shipped public smokes map: [references/shipped-surfaces.md](references/shipped-surfaces.md)
