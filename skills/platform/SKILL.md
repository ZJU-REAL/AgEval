---
name: bora-platform
description: BORA platform overview for coding agents — authority, red lines, what is shipped.
---

# BORA platform overview

**Bounded Orchestration for Runtime Agents** — Harness 的 Harness.

## Authority (read order)

1. `docs/design/` — product/mechanism truth
2. `ARCHITECTURE.md` — module tree / ownership
3. `specs/ROADMAP.md` — version acceptance
4. Active Specs — one increment

## What BORA owns vs package owns

| BORA Core | Package Harness |
| --- | --- |
| lock, Attempt identity, Provider isolation | business loop / roles |
| Capability projection, hard ceilings | local tools / params |
| Agent Service invoke + trajectory | publishing artifacts |
| Independent evaluator barrier | evaluator *algorithm* only |

## Red lines

- Trajectory ≠ PASS. Only independent evaluator forms PASS.
- No secrets in lock / trajectory / examples.
- Adapters named by mechanism, not Benchmark/task.
- Skills describe **shipped** surfaces only — never invent CLI.

## Evidence grades

Do not claim `isolated` or `real-benchmark-verified` from a single happy path.
Current public smokes: `examples/core/*`, `examples/l1/*`, `examples/journeys/*`.

## See also

- CLI: `skills/cli/SKILL.md`
- Config: `skills/config-package/SKILL.md`
- SDK: `skills/sdk-harness/SKILL.md`
- Design: `docs/design/00-overview-and-product.md`, `docs/design/01-bora-core.md`
