---
name: bora-config-package
description: >
  Author and review BORA Databases and Task members (Database bora.yaml + tasks/*/task.yaml,
  harness/evaluator entrypoints, agent_profiles, provider local|docker, limits hard ceilings,
  artifacts, evaluation inputs, gold isolation, allowlisted overrides). Use when creating or
  editing packages under examples/, writing bora.yaml/task.yaml, adding profiles/executors,
  declaring limits, wiring evaluation inputs, or reviewing package ownership violations.
  Triggers: "bora.yaml", "task.yaml", "database", "task package", "agent_profiles",
  "evaluation gold", "workspace_output", "provider kind", "package layout". Never put secrets
  in yaml; never branch adapters by benchmark name.
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
├── shared/                  # optional Dataset-level share (#65)
│   ├── lib/                 # import only (Harness + Evaluator PYTHONPATH)
│   ├── assets/              # read-only domain data via code paths
│   └── README.md
└── tasks/
    └── my-task/             # task_id == directory name
        ├── task.yaml        # bora.task/1 — role slots + intent (no entry/model)
        ├── harness.py       # prefer thin entry; orchestration in shared/lib
        ├── evaluator.py     # prefer thin entry; scoring in shared/lib
        ├── environment/     # optional seed.sql; Docker L1 needs Dockerfile
        ├── evaluation/      # gold / hidden — not for Agent mount
        ├── solution/        # human/CI offline fixture only; default NOT agent-seeded
        ├── lib/             # task-only; MUST NOT collide with shared/lib names
        └── data/            # agent-visible seed (L1: Runtime copies into workspace)
```

### Directory role map

| Dir | Who seeds / mounts | Agent-visible? | Eval-only? | Notes |
| --- | --- | --- | --- | --- |
| `tasks/*/data/` | Runtime L1 `seed_l1_workspace` copies files into Attempt workspace | Yes (after seed) | No | Prefer file-into-workspace here over Dockerfile `COPY` |
| `tasks/*/evaluation/` | Evaluator process after writer barrier | **No** | **Yes** | Gold / hidden labels only |
| `tasks/*/environment/` | Provider build/prepare (Dockerfile, seed.sql) | Indirect (image) | No | L1 image contract; not Agent mount of gold |
| `tasks/*/solution/` | Only when offline fixture flag / `BORA_L1_USE_SOLUTION=1` / offline agent | Default **No** | No | Human/CI fixture; **not** default Agent seed |
| `shared/lib/` | PYTHONPATH inject for Harness + Evaluator | **No** (import only) | No | Bridge/glue; never gold |
| `shared/assets/` | Code paths in Harness/Evaluator | **No** default mount | No | Domain fixtures via imports, not workspace |
| `scripts/` | Maintainer host only | No | No | Generators; not package runtime |

### Dataset `shared/` (when multi-task reuse)

| Put in… | Use for |
| --- | --- |
| `shared/lib/` | Bridge / domain glue **shared by many tasks** |
| `tasks/<id>/lib/` | **Only this task** extensions |
| `shared/assets/` | Read-only fixtures/policies via **code paths** (no `task.yaml` asset declaration) |
| `tasks/<id>/evaluation/` | Gold only — **never** under `shared/` |

**Hard rules agents must respect:**

1. **No top-level import name collision** between `shared/lib/` and any `tasks/*/lib/`
   (e.g. both cannot define `bridge.py` or package dir `bridge/`). Lock **hard-fails**.
2. Before adding modules, list both trees; prefer unique prefixes (`airline_bridge` vs task-local).
3. Changing `shared/` changes whole-package `packageDigest` (no separate shared sub-digest).
4. Core does **not** auto-COPY `shared/` into L1 images — task `environment/Dockerfile` must
   `COPY` explicitly if the container needs those files (see `references/isolation.md`).
5. Default: `shared/` is **not** mounted into the Agent workspace (Harness/Evaluator only).
6. **Import contract:** task code must **not** own a top-level package name `shared`. Prefer
   `shared.lib.*` (post-#68 namespaced inject) or documented path inject
   `[task_dir, database_root]` so `from shared.lib…` / `from lib…` resolve predictably.
   Collision gates stay in Runtime/lock (#68); authors follow the names here.

**Acceptance gate (run before claiming package OK):**

```bash
uv run python scripts/check_shared_lib_collisions.py <database-root>
```

### Multi-task conversion & generators

When many members are **isomorphic** (same harness/evaluator shape, different scenario
ids), **do not** hand-copy 50 task trees. Use a Dataset-root generator:

| Pattern | Guidance |
| --- | --- |
| Thin task entries | `tasks/<id>/{task.yaml,harness.py,evaluator.py}` are thin wrappers; orchestration lives in `shared/lib` |
| Regenerate from upstream | `scripts/generate_package.py` (or similar) reads upstream assets → writes members |
| Maintainer docs | Short `scripts/README.md` (or package README section): how to regenerate, required host deps, fork onboarding |
| Reference shape | `examples/tau3-airline/scripts/`, `examples/marble-coding/scripts/`, `examples/terminal-bench-2/scripts/` |

See [references/conversion.md](references/conversion.md) for owner-map checklist and
upstream → BORA placement template.

### Thin harness / evaluator (multi-task)

Prefer:

```python
# tasks/<id>/harness.py — thin entry only
from shared.lib.harness_core import run  # or lib.harness_core after path inject
# re-export or one-liner async def run(ctx): return await run_core(ctx, task_id=...)
```

Not: full dual-agent loop + tools inlined in every `tasks/*/harness.py`.  
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

# Role slots only — NO executor / entry / model / api_key here (#59).
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
    options:
      entry: opencode       # registry: codex | claude-code | pi | opencode | grok-build
    model: entry-default
    api_key: glm_coding_api_key   # env *locator name* only
  # HTTP / non-ACP example:
  # http-solver:
  #   executor: openai-http
  #   model: glm-4.7
  #   base_url: https://open.bigmodel.cn/api/coding/paas/v4
  #   api_key: zhipu_coding_api_key
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

## Scenario 同构与 Dataset 切包（Hub Leaderboard 可比性）

**默认：一个上游 scenario / 一种稳定 agent·role 拓扑 = 一个 Database（Dataset）。**

| 原则 | 说明 |
| --- | --- |
| 按 scenario 切包 | 例：MultiAgentBench **coding** → 一个 Dataset；database / werewolf 另包。不要默认把多 scenario 糊进一个 `bora.yaml` 还期望 Harbor 式可比榜。 |
| scenario 内同构 | 同一 Dataset 内尽量固定 `agent_profiles` 拓扑（role 数、id、协作形状）；task 业务参数可不同。 |
| 混装可允许 | 不同 task 可用不同 **role id**（拓扑可混）；job 轴是 Database 根 **`profiles.yaml`**。Hub Leaderboard（#40/#59）按 **job_overlay / profiles 绑定** 展示与复跑，不因角色槽拓扑不同而隐藏。 |
| Multi 榜行 | 默认按 **整配置组合**（指纹）一行；仅包内同构时可考虑 role 子列（后置 UI）。 |
| 上游复刻 | 填 `provenance`；**禁止**按 benchmark 名分支 adapter。 |

### Suite summary 自检字段

`bora run` suite / Always-k 结束写入 `.bora/suite-runs/<id>/summary.json`：

| 字段 | 含义 |
| --- | --- |
| `config_fingerprint` | `sha256:…` over 规范化 `actors_summary`（无 secret / 无 api_key） |
| `config_homogeneous` | suite 级 job 轴（`profiles.yaml` / `job_overlay`）一致 → `true`；角色槽拓扑不同**不**算不一致 |
| `actors_summary` | `[{profile_id, entry, model}, …]` |
| `agent_label` / `model_label` | 同构时从 actors 派生；异构时留空 |
| `metrics.pass_rate` / `mean_score` | 观测聚合（非 suite PASS） |
| `metrics.pass_at_k` / `pass_power_k` | Always-k job 指标（按 task mean）；**不进** fingerprint |
| `metrics.n_attempts` / `k_values` / `per_task` | job k 预算、k 列表、per-task n/c 审计（CLI only） |
| `task_refs[]` | 可含 `n` / `c` / `attempt_run_ids`（多 attempt 审计与 `--with-attempts`） |

**禁止**在 `task.yaml` / `bora.yaml` 增加 `n_attempts`。Always-k 只走 `bora run -k` / job 参数。

Upload（`bora results upload-suite`）**投影**这些字段到 Registry；缺 k maps 时本地 **ensure/recompute** 后再 POST；Hub **不**在 upload 时解 tar 硬提配置，也**不** live 算 pass@k。

**Hub Leaderboard 消费（#40 / #59 / #60）：**

- 有 `job_overlay` / `config_fingerprint` → 榜上展示 binding（yaml 形态可展开导出）  
- 有 `metrics.pass_at_k` 时额外列 **n_attempts** / **pass@k** / **pass^k**（缺省 `—`；默认排序仍 Pass rate → Mean score）  
- pass@k **不是** job 身份键；不同 k 可并列  
- `config_homogeneous: false` 仅当 **同一 role 的 entry/model 冲突**（异常）；正常多拓扑合集仍为 true  
- 指纹缺失（旧产物）→ 降级：仅 label，或提示「缺少 config 指纹」  



指纹**只服务可比性与展示**，**不是** suite PASS；PASS 仍只来自 per-task evaluator。

## Which `executor` / ACP `entry` values?

```bash
uv run bora executors          # .supported + host readiness
uv run bora executors -v       # + acp_entries[] (entry_id, engine/acp readiness, credential env *names*)
```

| Surface | Meaning |
| --- | --- |
| `.supported` | Valid `agent_profiles[].executor` values (this install): typically `acp`, `openai-http`, … |
| `.acp_entries[]` | When `executor: acp`, valid `options.entry` ids + host binary readiness |
| `.host_ready` | Kinds that can run here (ACP needs at least one ready entry; HTTP needs no CLI) |

**Target (coding agents):** `executor: acp` + `options.entry: <registry-id>`.  
**Do not** write `executor: codex|pi|opencode|claude-code` — lock fails (`unsupported_capability`) or L1 fails (`migrated_to_acp`).

Do not invent kinds or entry ids.

## Profile / binding switch without harness edits

1. Edit Database `profiles.yaml` bindings (role id → entry/model).
2. Or CLI alternate file: `bora run ... --profiles path/to/profiles.yaml`
3. Or CLI leaf override: `bora run ... --set '/bindings/solver/options/entry="pi"'`
4. Campaign matrix may use `/bindings/<role>/model|executor|options/entry=[…]`
5. Intent `limits.*` are **not** overridable via `--set`.

## Detail

- Field catalog & allowlists: [references/bora-yaml.md](references/bora-yaml.md)
- Isolation / gold / L1 / Dockerfile tiers / `data/` seed: [references/isolation.md](references/isolation.md)
- Conversion / generators / upstream owner map: [references/conversion.md](references/conversion.md)
