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
3. Emit thin `harness.py` / `evaluator.py` that import **`shared.lib.*`**
   (never bare leaf imports that assumed `shared/lib` on `PYTHONPATH`).
4. Write per-task `data/` (agent-visible) and `evaluation/` (gold) as needed.
5. Ensure package markers: `shared/__init__.py`, `shared/lib/__init__.py` (recommended).
6. Stay idempotent: re-run regenerates members without hand-editing fifty files.

Document regenerate steps in `scripts/README.md` or the package README so forks
do not invent Core hooks.

### Import migration (generators & ports)

| Old (leaf inject) | New (Database root on path) |
| --- | --- |
| `from harness_core import run` | `from shared.lib.harness_core import run` |
| `from bridge import make_environment` | `from shared.lib.bridge import make_environment` |
| `from evaluator_core import evaluate` | `from shared.lib.evaluator_core import evaluate` |
| task-local `from helper import …` via `lib/` on path | `from lib.helper import …` with `tasks/<id>/lib/` |

## Upstream → BORA owner map (checklist)

| Upstream concept | Put under | Consumer | Never |
| --- | --- | --- | --- |
| Instruction / prompt / agent-visible files | `tasks/<id>/data/` | Agent (L1 seed) / harness params | Gold under `data/` |
| Hidden tests / labels / expected answers | `tasks/<id>/evaluation/` | Evaluator only | `shared/`, Agent mount |
| Container image / apt / system deps | `tasks/<id>/environment/Dockerfile` | Provider L1 build | Runtime `apt`/`pip` as parity default; unpinned extras on `bora-attempt:l1` |
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
shared/
  __init__.py
  lib/
    __init__.py
    harness_core.py      # async run(ctx, *, task_dir) orchestration
    evaluator_core.py    # evaluate(...) scoring
    bridge.py            # tools / domain glue
tasks/task-00/
  harness.py             # from shared.lib.harness_core import run as _run
  evaluator.py           # from shared.lib.evaluator_core import evaluate as _evaluate
  data/ … evaluation/
```

Do not fork Core Runtime for “setup hooks”; use `data/` seed + Dockerfile tiers
(see `isolation.md`) and package-local glue only.

## Replicating an upstream image on `bora-attempt:l1`

When the port keeps BORA’s official base (`FROM bora-attempt:l1`) instead of
`FROM` the vendor instance image, **re-check every migrated `RUN pip` / `apt`
against this base** before claiming the eval env works:

- Upstream Dockerfiles assume *their* Python (often 3.6–3.11) and *their*
  frozen requirements. Ours is 3.12 + current indexes unless you pin.
- Bake an import that the hidden tests / conftest actually execute (not just
  `import pytest`). A green `docker build` that never imports `environmentfilter`
  / `astroid` 2.x / `urllib3` 1.x still ERROR at collection.
- Score after a real eval collect, not after `bora lock`. Image digest change
  is required after pin edits — old tags will keep the broken wheels.

Details: `references/isolation.md` § `FROM bora-attempt:l1` is not the upstream runtime.

## Evidence / claims

- Conversion completeness, Hub package publish, or `bora lock` success **do not**
  upgrade evidence grade (`runnable-mvp` / `isolated` / `real-benchmark-verified`).
- Import-style / path-inject changes **do not** upgrade evidence grade.
- PASS only from the independent evaluator after barrier.
- Fill `provenance` for ports; known gaps stay honest.

## Related

| Doc | Use for |
| --- | --- |
| `references/isolation.md` | L1 Dockerfile depth, `data/` seed, explicit `COPY shared/` + Database-root `PYTHONPATH` |
| Parent skill layout / role map | Where `shared/`, `scripts/`, `solution/` live; inject contract |
| `examples/tau3-airline/scripts/generate_package.py` | Reference generator emitting `shared.lib.*` |
