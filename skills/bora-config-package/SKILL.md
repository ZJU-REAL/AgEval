---
name: bora-config-package
description: >
  Author and review BORA Databases and Task members (Database bora.yaml + tasks/*/task.yaml,
  harness/evaluator entrypoints, agent_profiles, provider local|docker, limits hard ceilings,
  artifacts, evaluation inputs, gold isolation, allowlisted overrides). Use when creating or
  editing packages under examples/, writing bora.yaml/task.yaml, adding profiles/executors,
  declaring limits, wiring evaluation inputs, or reviewing package ownership violations.
  Triggers: "bora.yaml", "task.yaml", "profiles.yaml", "database", "task package",
  "agent_profiles", "evaluation gold", "workspace_output", "provider kind",
  "package layout". Never put secrets in yaml; never branch adapters by benchmark name.
---

# Config / Database + Task

Config Core is the **only** normative reader of package config. Delivery unit is a
**Database** root; each member has `task.yaml`. Harness must not re-read a second
“true config” over lock.

CLI: `bora lock|run <database-root> --task <task_id>` · `bora tasks <database-root>`.

## Layout

```text
my-database/                 # CLI path (bora.database/1)
├── bora.yaml                # Database identity / version / tasks.root
├── profiles.yaml            # job binding defaults (role id → entry/model/locator)
├── env.example              # documented credential locator names only
├── .env                     # local secrets (gitignore; never publish)
├── README.md                # author/run notes (optional but recommended)
├── scripts/                 # maintainer generators / regenerate (not on Agent path)
│   ├── README.md            # how to regenerate / fork onboarding (recommended)
│   └── generate_package.py  # multi-task thin members from upstream
├── shared/                  # optional Dataset package (shared/__init__.py recommended)
│   ├── lib/                 # import as shared.lib.* (Harness + Evaluator)
│   ├── assets/              # read-only domain data via code paths
│   └── README.md
└── tasks/
    └── my-task/             # task_id == directory name
        ├── task.yaml        # bora.task/1 — role slots + intent (no entry/model)
        ├── harness.py       # prefer thin entry; orchestration in shared.lib
        ├── evaluator.py     # prefer thin entry; scoring in shared.lib
        ├── environment/     # optional seed.sql; Docker L1 needs Dockerfile
        ├── evaluation/      # gold / hidden — not for Agent mount
        ├── solution/        # human/CI offline fixture only; default NOT agent-seeded
        ├── lib/             # task-only; import as lib.* (same stem as shared OK)
        └── data/            # agent-visible seed (L1: Runtime copies into workspace)
```

### Directory role map

| Dir | Who seeds / mounts | Agent-visible? | Eval-only? | Notes |
| --- | --- | --- | --- | --- |
| `tasks/*/data/` | Runtime L1 `seed_l1_workspace` copies files into Attempt workspace | Yes (after seed) | No | Prefer file-into-workspace here over Dockerfile `COPY` |
| `tasks/*/evaluation/` | Evaluator process after writer barrier | **No** | **Yes** | Gold / hidden labels only |
| `tasks/*/environment/` | Provider build/prepare (Dockerfile, seed.sql) | Indirect (image) | No | L1 image contract; not Agent mount of gold |
| `tasks/*/solution/` | Only when offline fixture flag / `BORA_L1_USE_SOLUTION=1` / offline agent | Default **No** | No | Human/CI fixture; **not** default Agent seed |
| `shared/lib/` | Import only via Database root on path | **No** (import only) | No | Bridge/glue; never gold |
| `shared/assets/` | Code paths in Harness/Evaluator | **No** default mount | No | Domain fixtures via imports, not workspace |
| `scripts/` | Maintainer host only | No | No | Generators; not package runtime |

### Dataset `shared/` (when multi-task reuse)

| Put in… | Use for | Import |
| --- | --- | --- |
| `shared/lib/` | Bridge / domain glue **shared by many tasks** | `from shared.lib.xxx import …` |
| `tasks/<id>/lib/` | **Only this task** extensions | `from lib.yyy import …` |
| `shared/assets/` | Read-only fixtures/policies via **code paths** (no `task.yaml` asset declaration) | code paths |
| `tasks/<id>/evaluation/` | Gold only — **never** under `shared/` | evaluator only |

**Import inject contract (Runtime — both harness worker and L0 evaluator):**

```text
sys.path prefix:  [task_dir, database_root, ...]
# Never inject shared/lib or tasks/<id>/lib as path roots
```

| Wanted | Meaning |
| --- | --- |
| `from shared.lib.bridge import …` | Dataset glue under `shared/lib/` |
| `from lib.helper import …` | Task-only under `tasks/<id>/lib/` |

Recommend real packages: `shared/__init__.py`, `shared/lib/__init__.py`, and
`tasks/<id>/lib/__init__.py` when using `from lib…`.

**Hard rules agents must respect:**

1. **Reserved top-level name `shared`:** task members must **not** own
   `tasks/<id>/shared/` or `tasks/<id>/shared.py` (shadows Dataset package on path).
   Lock **hard-fails**. Same stem under `shared/lib` and `tasks/*/lib` (e.g. both
   `bridge.py`) is **allowed** — namespaces differ (`shared.lib.bridge` vs `lib.bridge`).
2. Changing `shared/` changes whole-package `packageDigest` (no separate shared sub-digest).
3. Core does **not** auto-COPY `shared/` into L1 images — task `environment/Dockerfile`
   must `COPY shared/` and put **Database root** (not only `shared/lib` leaf) on
   `PYTHONPATH` if the container must import `shared.lib.*` (see `references/isolation.md`).
   L0 inject ≠ L1 automatic availability.
4. Default: `shared/` is **not** mounted into the Agent workspace (Harness/Evaluator only).
5. **Migration:** bare `from bridge import …` (old leaf inject) →
   `from shared.lib.bridge import …`. Generators must emit namespaced imports.

**Acceptance gate (run before claiming package OK):**

```bash
uv run python scripts/check_shared_lib_collisions.py <database-root>
```

### Multi-task conversion & generators

When many members are **isomorphic** (same harness/evaluator shape, different scenario
ids), **do not** hand-copy 50 task trees. Use a Dataset-root generator:

| Pattern | Guidance |
| --- | --- |
| Thin task entries | `tasks/<id>/{task.yaml,harness.py,evaluator.py}` are thin wrappers; orchestration lives in `shared.lib` |
| Regenerate from upstream | `scripts/generate_package.py` emits `from shared.lib…`, not bare leaf imports |
| Maintainer docs | Short `scripts/README.md` (or package README section): how to regenerate, required host deps, fork onboarding |
| Reference shape | `examples/tau3-airline/scripts/` (and other multi-task `examples/*/scripts/` when present) |

See [references/conversion.md](references/conversion.md) for owner-map checklist and
upstream → BORA placement template.

### Thin harness / evaluator (multi-task)

Prefer:

```python
# tasks/<id>/harness.py — thin entry only
from shared.lib.harness_core import run as _run

async def run(ctx):
    return await _run(ctx, task_dir=Path(__file__).resolve().parent)
```

Optional task-only helpers:

```python
from lib.task_only import helper  # tasks/<id>/lib/task_only.py
```

Not: full dual-agent loop + tools inlined in every `tasks/*/harness.py`.  
Not: bare `from harness_core import …` (depends on removed `shared/lib` leaf inject).  
SDK surface stays the same (`Agent.session…invoke`); see `bora-sdk-harness` for API,
this skill for **where** multi-task code lives.

### `solution/` semantics

- **Purpose:** human inspection, CI offline fixture, offline-agent demos.
- **Default:** Runtime does **not** seed `solution/` into the Agent workspace.
- **Exception (author-level):** L1 offline path when `BORA_L1_USE_SOLUTION=1` or
  offline-agent allow — files under `solution/` may be copied into workspace and
  `solution_seed` is recorded in L1 meta. Do not treat that as production Agent path.
- Never put gold-only labels in `solution/`; gold stays under `evaluation/`.

### Evidence discipline (ports)

| Claim | Valid? |
| --- | --- |
| Package exists / converts / Hub publish succeeds | **≠** evidence-grade upgrade |
| `bora lock` OK | **≠** `runnable-mvp` / `isolated` |
| Harness `completed` or trajectory present | **≠** PASS |
| Independent evaluator status | Only PASS authority |

Fill `provenance` for ports/reimplementations. Do not invent public smoke claims
from conversion completeness alone.

## Minimal Database `bora.yaml`

```yaml
format: bora.database/1
database_id: org/my-suite
version: "0.1.0"
tasks:
  root: tasks
# optional defaults (suite scheduling only — not Always-k):
# defaults:
#   max_concurrent_tasks: 1
# n_attempts / -k is CLI/job only — never a package field
```

## Minimal member `task.yaml` skeleton (role slots only)

```yaml
format: bora.task/1
task_id: my-task

harness:
  runtime: python
  entrypoint: harness:run

parameters:
  models:
    default: solver          # role id only
  # active_profile: solver   # optional; overridable via CLI --set
  # Non-empty agent_profiles ⇒ Agent Service; harness owns session/invoke.

provider:
  kind: local               # or docker for L1
  assurance: l0             # docker L1 packages use assurance: l1 intent

# Role slots only — NO executor / entry / model / api_key here (job binding is profiles.yaml).
agent_profiles:
  - id: solver

limits:                     # task contract — not job-overridable
  wall_time_seconds: 300
  agent_invocations: 2
  environment_actions: 0

artifacts:
  publishable:
    - id: session-output
      producer: harness
      path: artifacts/session-output.json
      media_type: application/json

evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  # tmpfs_mb: 256          # optional L1 clean-eval /tmp (MiB); omit → 32. Not limits.*
  inputs:
    - artifact: session-output
      target: artifacts/session-output.json
  output:
    format: json
```

## Database `profiles.yaml` (job binding)

```yaml
format: bora.profiles/1
bindings:
  solver:
    executor: acp
    extensions:
      - plugin: acp
        options:
          entry: opencode       # registry: codex | claude-code | pi | opencode | grok-build
    model: entry-default
    api_key: ${glm_coding_api_key}   # ${ENV_NAME} locator; value never in YAML/lock
  # HTTP / non-ACP example:
  # http-solver:
  #   executor: openai-http
  #   model: glm-4.7
  #   base_url: ${OPENAI_BASE_URL}
  #   api_key: ${zhipu_coding_api_key}
```

## Ownership rules

| Field | Consumer |
| --- | --- |
| `parameters` | Harness `ctx.params` only |
| envelope / profiles / limits / provider | Runtime |
| gold under `evaluation/` | Clean evaluator after barrier — **not** Agent/Harness mount |
| `provenance` | Config / authors / auditors only — **not** PASS |

- Never put API keys or passwords in yaml.
- Do not branch harness on executor kind / ACP entry for Core behavior; switch profile instead.
- Adapter modules must stay mechanism-named (`acp`, `postgresql`, docker) — not benchmark names.
- For **ports / reimplementations**, fill `provenance` (see `references/bora-yaml.md`); Attempt PASS still comes only from the independent evaluator.

## Scenario homogeneity & Dataset packaging (Hub Leaderboard comparability)

**Default: one upstream scenario / one stable agent·role topology = one Database (Dataset).**

| Principle | Guidance |
| --- | --- |
| Split by scenario | e.g. MultiAgentBench **coding** → one Dataset; database / werewolf as separate packages. Do not default-merge multiple scenarios into one `bora.yaml` and expect Harbor-style comparable boards. |
| Homogeneous within scenario | Keep `agent_profiles` topology fixed inside a Dataset (role count, ids, collaboration shape); task business parameters may differ. |
| Mixed packs allowed | Different tasks may use different **role ids** (topology may mix); the job axis is Database-root **`profiles.yaml`**. Hub Leaderboard displays and re-runs by **job_overlay / profiles binding**, and does **not** hide rows just because role-slot topology differs. |
| Multi board rows | Default one row per **full config combination** (fingerprint); role sub-columns only when the pack is homogeneous (later UI). |
| Upstream ports | Fill `provenance`; **never** branch adapters by benchmark name. |

### Suite summary self-check fields

`bora run` suite / Always-k end writes `.bora/suite-runs/<id>/summary.json`:

| Field | Meaning |
| --- | --- |
| `config_fingerprint` | `sha256:…` over normalized `actors_summary` (no secrets / no api_key) |
| `config_homogeneous` | Suite-level job axis (`profiles.yaml` / `job_overlay`) consistent → `true`; different role-slot topology does **not** count as inconsistent |
| `actors_summary` | `[{profile_id, entry, model}, …]` |
| `agent_label` / `model_label` | Derived from actors when homogeneous; empty when heterogeneous |
| `metrics.pass_rate` / `mean_score` | Observational aggregates (not suite PASS) |
| `metrics.pass_at_k` / `pass_power_k` | Always-k job metrics (by task mean); **not** in fingerprint |
| `metrics.n_attempts` / `k_values` / `per_task` | Job k budget, k list, per-task n/c audit (CLI only) |
| `task_refs[]` | May include `n` / `c` / `attempt_run_ids` (multi-attempt audit and `--with-attempts`) |

**Do not** add `n_attempts` to `task.yaml` / `bora.yaml`. Always-k is CLI/job only (`bora run -k` / job params).

Upload (`bora results upload-suite`) **projects** these fields to the Registry; if k maps are missing, **ensure/recompute** locally then POST. Hub does **not** unpack tars at upload to hard-extract config, and does **not** live-compute pass@k.

**Hub visibility (paired with Leaderboard comparability):**

| Goal | Correct path | Wrong expectation |
| --- | --- | --- |
| Dataset **Leaderboard** has a row | Bind a **release** (`bora publish --draft` then `bora release`, or a direct `bora publish`) → `bora run <db>` (**omit** `--task`) → `upload-suite --suite-run <id>` of a **complete** suite | Only `bora run --task` + `results upload`; or a draft-bound / incomplete suite (attempt or Jobs may exist; **board** often missing) |
| Task **Jobs** openable trajectory | `upload-suite --with-attempts` (or later upload the run_id attached under suite `task_refs`) | Attempt-only upload, no suite row |

Fingerprint / binding display requires a **suite row already uploaded** (with `job_overlay` / `config_fingerprint`).

**Hub Leaderboard consumption:**

- With `job_overlay` / `config_fingerprint` → board shows binding (yaml form expandable/exportable)
- With `metrics.pass_at_k` → extra columns **n_attempts** / **pass@k** / **pass^k** (default `—`; sort still Pass rate → Mean score)
- pass@k is **not** a job identity key; different k may sit side by side
- `config_homogeneous: false` only when **same role has conflicting entry/model** (anomaly); normal multi-topology packs stay true
- Missing fingerprint (legacy artifacts) → degrade: labels only, or prompt “missing config fingerprint”

Fingerprint is **only for comparability and display**, **not** suite PASS; PASS still comes only from the per-task evaluator. Ops detail: `$bora-cli` § Hub visibility.

## Which `executor` / ACP `entry` values?

```bash
uv run bora executors          # .supported + host readiness
uv run bora executors -v       # + acp_entries[] (entry_id, engine/acp readiness, credential env *names*)
uv run bora plugin list        # installed mechanism plugins (e.g. nooa)
```

| Surface | Meaning |
| --- | --- |
| `.supported` | Valid `agent_profiles[].executor` values (this install): typically `acp`, `openai-http`, … |
| `.acp_entries[]` | When `executor: acp`, valid `options.entry` ids + host binary readiness |
| `.host_ready` | Kinds that can run here (ACP needs at least one ready entry; HTTP needs no CLI) |
| Installed plugins | Extra executor plugin_ids after `bora plugin install` (Recognition only) |

**Target (coding agents):** `executor: acp` + `- plugin: acp` / `options.entry: <registry-id>`.  
**Do not** write `executor: codex|pi|opencode|claude-code` — lock fails (`unsupported_capability`) or L1 fails (`l1_executor_unbound`).

**External mechanism (e.g. nooa):** `executor: nooa` + `- plugin: nooa` / `options.agent: "lib.agents:Class"` in
**profiles only** — never in member `task.yaml`. `bora plugin install` does **not** rewrite
profiles. `bora lock` writes full `extension_bindings` for the resolved extension graph.

Do not invent kinds or entry ids.

## Profile / binding switch without harness edits

1. Edit Database `profiles.yaml` bindings (role id → entry/model).
2. Or CLI alternate file: `bora run ... --profiles path/to/profiles.yaml`
3. Or CLI leaf override: `bora run ... --set '/bindings/solver/options/entry="pi"'`
4. Campaign matrix may use `/bindings/<role>/model|executor|options/<key>=[…]`
5. Intent `limits.*` are **not** overridable via `--set`.

## Detail

- Field catalog & allowlists: [references/bora-yaml.md](references/bora-yaml.md)
- Isolation / gold / L1 / Dockerfile tiers / `data/` seed: [references/isolation.md](references/isolation.md)
- Conversion / generators / upstream owner map: [references/conversion.md](references/conversion.md)
- New mechanism plugin (`bora.plugin/1`): `$bora-plugin`
