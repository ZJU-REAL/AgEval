# Conversion & multi-task package authoring

Author-facing patterns for porting upstream benchmarks into a BORA Database.
Runtime / schema behavior is unchanged — this is placement and maintainability only.

## When to use a generator

| Signal | Action |
| --- | --- |
| ≥ ~5 isomorphic members (same harness/eval shape) | Prefer `scripts/generate_package.py` (or equivalent) |
| Members differ only by scenario id / params / data | Thin `task.yaml` + `data/` / `evaluation/` per task; shared orchestration |
| One-off demo task | Inline harness is fine; still respect gold isolation |

### Generator shape (reference)

Existing examples under `examples/*/scripts/generate_package.py` typically:

1. Read upstream assets (often under `shared/assets/` or an external path).
2. Emit `tasks/<task_id>/task.yaml` with `provenance` filled.
3. Emit thin `harness.py` / `evaluator.py` that import Dataset glue (`shared.lib.*` or path-injected `lib.*`).
4. Write per-task `data/` (agent-visible) and `evaluation/` (gold) as needed.
5. Stay idempotent: re-run regenerates members without hand-editing fifty files.

Document regenerate steps in `scripts/README.md` or the package README so forks
do not invent Core hooks.

## Upstream → BORA owner map (checklist)

| Upstream concept | Put under | Consumer | Never |
| --- | --- | --- | --- |
| Instruction / prompt / agent-visible files | `tasks/<id>/data/` | Agent (L1 seed) / harness params | Gold under `data/` |
| Hidden tests / labels / expected answers | `tasks/<id>/evaluation/` | Evaluator only | `shared/`, Agent mount |
| Container image / apt / system deps | `tasks/<id>/environment/Dockerfile` | Provider L1 build | Runtime `apt`/`pip` as parity default |
| Domain tools / bridge / dual-agent loop | `shared/lib/` (multi-task) or `tasks/<id>/lib/` (one-off) | Harness + Evaluator import | Gold files |
| Shared policies / DB dumps / static assets | `shared/assets/` | Code paths | Agent default mount of gold |
| Offline known-good workspace files | `tasks/<id>/solution/` | Human / CI / offline flag only | Default Agent seed |
| Maintainer regenerate / fork scripts | `scripts/` | Host maintainers | Attempt PYTHONPATH |
| Job binding (executor / entry / model) | Database `profiles.yaml` | Runtime / job overlay | Secrets in yaml |

## Scenario cut (stable topology)

Default conversion rule (aligns with Hub leaderboard comparability):

- **One upstream scenario / one stable role topology → one Database** (`bora.yaml`).
- Keep `agent_profiles` role ids and collaboration shape stable inside the Dataset.
- Vary task business parameters and `data/` / `evaluation/` per member, not role topology.
- Different scenarios (e.g. coding vs werewolf) → separate Datasets, not one mixed package
  expecting a single Harbor-style board.

Job axis remains Database-root `profiles.yaml` / CLI overlays — not per-task executor names.

## Thin multi-task harness template

```text
shared/lib/
  harness_core.py      # async run(ctx, *, task_id) orchestration
  evaluator_core.py    # evaluate(...) scoring
  bridge.py            # tools / domain glue
tasks/task-00/
  harness.py           # from shared.lib.harness_core import run  (or re-export)
  evaluator.py         # thin
  data/ … evaluation/
```

Do not fork Core Runtime for “setup hooks”; use `data/` seed + Dockerfile tiers
(see `isolation.md`) and package-local glue only.

## Evidence / claims

- Conversion completeness, Hub package publish, or `bora lock` success **do not**
  upgrade evidence grade (`runnable-mvp` / `isolated` / `real-benchmark-verified`).
- PASS only from the independent evaluator after barrier.
- Fill `provenance` for ports; known gaps stay honest.

## Related

| Link | Relation |
| --- | --- |
| Issue #69 | Skill series A–B |
| Issue #65 / #68 | `shared/` hard rules + import namespaces |
| Issue #66 | Conversion epic / example packages |
| `references/isolation.md` | L1 Dockerfile depth, `data/` seed, `COPY shared/` |
