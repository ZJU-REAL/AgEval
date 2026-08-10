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
└── tasks/
    └── my-task/             # task_id == directory name
        ├── task.yaml        # bora.task/1 — role slots + intent (no entry/model)
        ├── harness.py
        ├── evaluator.py
        ├── environment/     # optional seed.sql; Docker L1 needs Dockerfile
        ├── evaluation/      # gold / hidden — not for Agent mount
        ├── lib/
        └── data/
```

## Minimal Database `bora.yaml`

```yaml
format: bora.database/1
database_id: org/my-suite
version: "0.1.0"
tasks:
  root: tasks
# optional defaults (suite scheduling only):
# defaults:
#   max_concurrent_tasks: 1
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
| 混装可允许 | single+multi 或多拓扑混装**允许**，但 suite 会标 `config_homogeneous: false`；Hub Leaderboard（#40）**拒绝按可比榜展示**（空态 + 可读提示），原始 suite 仍可进 Task Jobs / 运维列表。 |
| Multi 榜行 | 默认按 **整配置组合**（指纹）一行；仅包内同构时可考虑 role 子列（后置 UI）。 |
| 上游复刻 | 填 `provenance`；**禁止**按 benchmark 名分支 adapter。 |

### Suite summary 自检字段

`bora suite` / suite run 结束写入 `.bora/suite-runs/<id>/summary.json`：

| 字段 | 含义 |
| --- | --- |
| `config_fingerprint` | `sha256:…` over 规范化 `actors_summary`（无 secret / 无 api_key） |
| `config_homogeneous` | 本 suite 各 task 实际 profiles 配置一致 → `true` |
| `actors_summary` | `[{profile_id, entry, model}, …]` |
| `agent_label` / `model_label` | 同构时从 actors 派生；异构时留空 |

Upload（`bora results upload-suite`）**投影**这些字段到 Registry；Hub **不**在 upload 时解 tar 硬提配置。

**Hub Leaderboard 消费（#40）：**

- `config_homogeneous: true` + 有指纹 → 正常榜行  
- `config_homogeneous: false` → **不进可比榜**（提示「配置不一致，难以比较」）  
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
- Isolation / gold / L1 notes: [references/isolation.md](references/isolation.md)
