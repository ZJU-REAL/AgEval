# ageval

**agent eval** — 锁定 dataset，选定环境，运行任务，由独立 evaluator 给出评分。

[English](README.md)

[![Release](https://img.shields.io/github/v/release/ZJU-REAL/ageval?display_name=tag&sort=semver)](https://github.com/ZJU-REAL/ageval/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)

> Agent 评测通常只给**模型**打分，而把编排、隔离、可见性与评分权威留在各厂商 harness 中。更换 coding agent 或环境后，分数便失去可比性。
>
> **ageval** 是更换上述组件时仍保持不变的外层运行时：锁定 dataset，打开一个环境，执行题包 `run.py`，PASS 仅来自独立的 `evaluator.py`。Coding agent 通过 **ACP** 接入。其它后端以插件安装，再由 job profiles 绑定。

## 目录

- [是什么](#是什么)
- [如何运行](#如何运行)
- [功能](#功能)
- [快速开始](#快速开始)
- [架构](#架构)
- [目录结构](#目录结构)
- [文档](#文档)

## 是什么

ageval 是面向 Agent 的**有边界的评测运行时**，而不是又一个 Agent。

- **交付单位是 dataset**，而非某厂商 suite 的完整镜像。根目录为 `ageval.yaml`，成员为 `tasks/<id>/task.yaml`。CLI 路径始终是 dataset 根。
- **一次 Attempt 可见。** 阶段为 environment → run → evaluate → record，cleanup 在 `finally` 中执行。打开 `src/ageval/attempt/` 即可读出顺序。
- **环境是一个槽：** `local` / `docker` / `e2b` / `ssh`。Protocol 相同（`upload` / `exec` / `attach_stdio`）。更换 kind 时修改 `profiles.yaml`，无需改动 `run.py`。
- **Coding agent 为真实 CLI，经 ACP 接入**（pi、Codex、Claude、OpenCode、Grok 等）。Parent 是唯一的 JSON-RPC client。
- **其它后端为插件**（`ageval.plugin/1`）：nooa、dsh、miniswe。安装到本机缓存，再通过 profiles 绑定。install 不会改写 dataset。
- **PASS 并不等于 Agent 执行完成。** gold 上传之后才执行 `evaluator.py`。轨迹用于检查。

## 如何运行

```text
            你 ── lock / run ──►  ┌─────────────────┐
                                  │     Attempt     │  锁定 dataset · digest
                                  │   ageval core   │  environment → run
                                  │                 │  evaluate → record
                                  │                 │  finally cleanup
                                  └────────┬────────┘
                                           │ 打开一个环境
              ┌────────────────────────────┼────────────────────────────┐
              ▼                            ▼                            ▼
        ┌───────────┐                ┌───────────┐                ┌───────────┐
        │   local   │                │  docker   │                │ e2b / ssh │
        └─────┬─────┘                └─────┬─────┘                └─────┬─────┘
              └──────── Protocol: upload · exec · attach_stdio ─────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │     run.py      │  任务循环 · 调用 Agent
                                  │  ACP / plugin   │  executor 槽
                                  └────────┬────────┘
                                           ▼
                                  ┌─────────────────┐
                                  │  evaluator.py   │  PASS 的唯一来源
                                  └─────────────────┘
```

1. **锁定实验。** `ageval lock` 合并 dataset、task 与 profiles，校验能力，写出 digest。密钥仅作为 locator，不以明文写入 lock。
2. **打开一个环境。** kind 来自 `profiles.yaml` 的 `environment:`。`--probe` 仅执行 lock 与 preflight：缺少 `E2B_API_KEY` 或 SSH locator 时失败。
3. **运行任务，而非编排流水线。** `run.py` 负责循环、Tool 与 Agent 调用。ACP 从环境取得 `attach_stdio`；dsh / nooa / miniswe 使用 `exec` / `upload`。
4. **独立评分。** 停止写入进程，上传 gold（`evaluation/`），由 `evaluator.py` 绑定 PASS / FAIL / ERROR。cleanup 始终执行。

更换环境或 Agent 时，题包 `run.py` 无需修改。

## 功能

**运行**

- **`ageval lock` / `run` / `campaign`。** 单个任务、完整 suite（省略 `--task`），或同一任务上的参数矩阵。Always-k（`-k`）是 job 轴，不是 campaign 轴。
- **ACP entry。** 同一份 `run.py`，更换 `options.entry`（pi / Codex / Claude / OpenCode / Grok）。`--set` 仅覆盖白名单指针；`--profiles` 整体替换 job 文档。
- **Agent 包。** 安装 `ageval.agent/1` 后，在 lock / run / campaign 上使用 `--agent`。`--agent` 与 `--profiles` 互斥。
- **插件。** `ageval plugin install plugins/nooa`（或 `dsh`、`miniswe`），再绑定 `executor:` 与 `extensions`。docker 从插件包 bake 镜像层。
- **`--probe`。** 按当前绑定与环境输出 plan 与 readiness。不调用 Agent、不 bake、不修改 digest。

**环境**

- **四种 kind，一套 Protocol。** `local` 目录、`docker` 容器、`e2b` sandbox、`ssh` 远端。ACP 不 import docker / e2b / ssh。
- **gold 不进入 Agent 可见范围。** `evaluation/` 不会被 mount，仅在 evaluate 阶段 upload。
- **上限在调用前强制。** 墙钟、内存、进程与调用次数由 runtime 执行，不能由 `run.py` 自行提升。
- **ssh A** 不支持 live ACP stdio；journeys 的 ssh A profiles 使用 dsh / nooa 的 `exec`。默认 CI **不**将 e2b / ssh 的真实 Agent 运行标为已验证。

**查看结果**

- **`ageval view`。** 本机 Jobs → Tasks → Attempt。读取所打开 dataset 下的 `.ageval/suite-runs/` 与 `.ageval/runs/`。不连接 Registry。
- **`ageval evidence`。** 导出密封轨迹副本，不修改分数。
- **Hub + Registry。** 发布 dataset、插件与 Agent 包，上传 suite。公开榜仅收录完备且绑定 release 的 suite。组织 owner 管理成员、可见性、版本与 release。

**编写任务**

- **dataset 布局。** `ageval.yaml` + `profiles.yaml` + `tasks/<id>/{task.yaml,run.py,evaluator.py}`。可选 `environment/`、`shared/`。
- **`ageval_sdk`。** `RunContext`、`Agent.session`、Tool、终端——可选。SDK 不判定 PASS，也不持有宿主凭据。
- **机制插件。** 独占槽（`environment`、`executor`、`evaluation_runtime`、`trajectory_seal`）与链槽。按机制命名，不按 bench 名分支。

## 快速开始

需要 [uv](https://docs.astral.sh/uv/) 与 CPython **3.12+**。实际运行 coding agent 还需要本机 ACP 入口与凭据。仅执行 `ageval lock` 时不需要。

```bash
git clone https://github.com/ZJU-REAL/ageval.git
cd ageval
uv sync --frozen --all-packages
uv run ageval -V
```

```bash
uv run ageval tasks examples/journeys
uv run ageval lock examples/journeys --task terminal-jsonl-agg
uv run ageval run  examples/journeys --task terminal-jsonl-agg
uv run ageval run  examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.e2b-acp.yaml --probe
uv run ageval executors -v
uv run ageval view examples/journeys --no-browser
```

`examples/journeys` 的默认环境为 docker。先执行 `ageval agent install examples/agents/pi-default`，再使用 `--agent` 绑定。

仓库内示例见 [`examples/README.md`](examples/README.md)：journeys、`tau3-airline`，以及 Agent 目录包。

## 架构

```text
  ageval.yaml + task.yaml + profiles.yaml
                 │
                 ▼
           ageval lock                 digest · extension_bindings
                 │
                 ▼
           ageval run  ── Attempt ── environment → run → evaluate → record
                 │                      finally cleanup
                 ▼
        .ageval/runs/<id>/             lock.json · result.json · trajectory.jsonl
                 │
      ┌──────────┼──────────┐
      ▼                     ▼
 ageval view          Registry / Hub
 本机 Jobs            publish · upload-suite · Leaderboard
```

- **Config Core** 是 dataset YAML 的唯一读取者。未知 format 返回一个 `invalid_format`。
- **Attempt** 拥有身份、deadline、cleanup 与 PASS 绑定。插件修改的是 lock 时的绑定，不重排这五个阶段。
- **CLI** 仅通过 `ageval.application.composition`。Hub 连接 Registry；Viewer 读取本机文件。

## 目录结构

由 [`ARCHITECTURE.md`](ARCHITECTURE.md) 简化。`.ageval/`、`.venv/` 等生成目录不算源码。

```text
ageval/
├── src/ageval/
│   ├── cli/                         # 参数、帮助、退出码
│   ├── application/
│   │   ├── composition.py           # 生产接线唯一入口；CLI 只 import 此处的 build_*
│   │   ├── lock.py                  # load_and_lock
│   │   ├── run.py                   # 签发身份 → run_attempt
│   │   ├── campaign.py / suite/     # 矩阵 · suite · Always-k
│   │   └── agent_ops/ / plugin_ops / registry_ops/
│   ├── attempt/                     # 可见流水线
│   │   ├── __init__.py              # run_attempt
│   │   └── phases/                  # environment → run → evaluate → record · cleanup
│   ├── config/                      # dataset + task.yaml + profiles
│   ├── environments/protocol.py     # EnvironmentProvider · 能力；不含厂商 SDK
│   ├── plugins/
│   │   ├── slots.py                 # 独占槽 / 链槽
│   │   └── contrib/                 # acp · local · docker · e2b · ssh
│   ├── runtime/                     # 身份、父进程 Agent Service、task_worker
│   ├── evaluation/                  # 评测屏障 + 绑定 PASS
│   └── evidence/                    # trajectory.jsonl 布局
├── sdk/python/                      # run.py 用的 ageval_sdk（不判定 PASS，不持有宿主凭据）
├── plugins/                         # 外置 ageval.plugin/1（nooa、dsh、miniswe 等）
├── examples/
│   ├── journeys/                    # terminal-jsonl-agg · tau2-dialog-min · multiagent-env-min
│   ├── tau3-airline/
│   └── agents/                      # ageval.agent/1
├── apps/viewer                      # ageval view SPA
├── apps/hub                         # Hub SPA
├── services/registry/               # 包与结果 HTTP
├── docker/attempt/                  # 官方镜像；ACP entry 在 build 期装入
├── docs/                            # 机制设计
└── website/                         # 产品文档
```

## 文档

- 用法：[website/](website/)
- 设计：[docs/](docs/README.md)
- 示例：[examples/README.md](examples/README.md)
- [AGENTS.md](AGENTS.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
