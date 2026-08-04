---
name: bora-platform
description: >
  BORA (Bounded Orchestration for Runtime Agents) platform map for coding agents:
  authority order (docs/design vs ARCHITECTURE vs ROADMAP vs Specs), Core vs package
  ownership, red lines (trajectory≠PASS, no secrets in lock/evidence, mechanism-named
  adapters only), evidence grades, and which sibling skill to load next. Use when an
  agent enters the BORA repo, needs orientation before changing code/packages, asks
  "what is BORA", "who owns PASS", "read order", "evidence grade", or which docs are
  authoritative. Not a substitute for docs/design; only routes and hard constraints.
---

# BORA platform

Harness 的 Harness：Runtime 管边界（lock、Attempt、隔离、Capability、轨迹、独立评测）；package 管业务 loop。

## Read order (do not invent authority)

1. `docs/design/` — product + mechanism (primary)
2. `ARCHITECTURE.md` — module ownership / dependency direction
3. `specs/ROADMAP.md` — version acceptance (Version Index)
4. `specs/active/*` — one implementable increment
5. Code / tests / examples — evidence of what is shipped

Conflict → stop; fix the highest authority artifact first, then sync downstream.

## Ownership split

| Owns | Does not own |
| --- | --- |
| **Core:** `load_and_lock`, Run/Trial/Attempt, Provider projection, Agent Service invoke+trajectory, hard ceilings, evaluator barrier, flat Result | Package business roles, scoring algorithms |
| **Package harness:** loop, roles, local Tools, handoff data, `ctx.params` | PASS/FAIL, credentials, isolation mounts |
| **Evaluator (package):** truth / score algorithm | Starting Agent, host secrets, rewriting runtime errors into PASS |

## Red lines (fail closed)

1. **Trajectory ≠ PASS** — only independent evaluator may form PASS. Missing trajectory must not invent PASS.
2. **No secrets** in lock, package yaml, evidence, export, or examples. Env vars are locators only.
3. **Adapters** named by mechanism/protocol/resource (`codex`, `pi`, `postgresql`, docker) — never Benchmark/task/domain names.
4. **Do not claim** suite-wide `isolated` or `real-benchmark-verified` from one happy path.
5. **Skills only describe shipped surfaces** — never invent CLI flags or Core APIs.

## Evidence grades (honest)

| Claim | Requires |
| --- | --- |
| `runnable-mvp` (L0) | Real public `bora run` + real Agent path (scoped journeys) |
| `assurance:l1` | Measured Docker combo only (see Result.l1 / execution_location) |
| `isolated` / `real-benchmark-verified` | Matching Roadmap acceptance — **not** inferred |

## Route to sibling skills

| Task | Load |
| --- | --- |
| Run CLI / interpret exit / export trajectory | `$bora-cli` |
| Write or review `bora.yaml` / package layout | `$bora-config-package` |
| Write harness / AgentSession / ToolSet | `$bora-sdk-harness` |

## Progressive detail

- Authority & conflicts: [references/authority.md](references/authority.md)
- Red-line checklist with examples: [references/red-lines.md](references/red-lines.md)
- Shipped public smokes map: [references/shipped-surfaces.md](references/shipped-surfaces.md)
