# ageval

<p align="center">
  <img src="docs/assets/hero.zh-CN.png" alt="ageval：Agent 评测写一次，到处都能跑。" width="100%">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">中文</a>
</p>
<p align="center">
  <a href="https://github.com/ZJU-REAL/ageval/stargazers"><img alt="stars" src="https://shieldcn.dev/github/stars/ZJU-REAL/ageval.svg?variant=secondary&size=sm&logo=ri%3AGoStarFill&logoColor=F5C518"></a>
  <a href="https://github.com/ZJU-REAL/ageval/blob/main/LICENSE"><img alt="license" src="https://shieldcn.dev/github/license/ZJU-REAL/ageval.svg?variant=secondary&size=sm&logo=ri%3AFaBalanceScale&logoColor=34D399"></a>
  <a href="https://github.com/ZJU-REAL/ageval/releases"><img alt="release" src="https://shieldcn.dev/github/release/ZJU-REAL/ageval.svg?variant=secondary&size=sm&logo=ri%3AGoTag&logoColor=60A5FA"></a>
  <a href="https://github.com/ZJU-REAL/ageval/commits"><img alt="last commit" src="https://shieldcn.dev/github/last-commit/ZJU-REAL/ageval.svg?variant=secondary&size=sm&logo=ri%3AGoGitCommit&logoColor=A78BFA"></a>
</p>

大多数 Agent 评测仍停留在**模型**：同一套提示、同一套工具约定，比较不同权重或不同 API。可交付的 Agent 却是模型加上它的运行时——同一套权重接到不同的 coding agent、工具策略或环境上，行为和成本都会变。配得上「比较」的评测因此是一个乘积：**H 个 Agent 运行时 × M 个模型 × E 个环境**。每个组合都要一套脚手架；组合不写进 lock，分数就不可比。

**ageval** 在统一运行基座上用插件切换待评测 Agent；装上 CLI 和 skill，Agent 能设计、转化 benchmark 并自动跑评测；在 Hub 上分享或复用 dataset、插件和 Agent 配置，并上传评测结果。

<p align="center">
  <img src="docs/assets/why-ageval.jpg" alt="N 种环境 × M 种 Agent 运行时：逐个组合需要 N·M 份定制脚手架；ageval 用插件组合环境和 Agent，一份 dataset 到处跑。" width="800">
</p>

## 目录

- [是什么](#是什么)
- [如何运行](#如何运行)
- [功能](#功能)
- [快速开始](#快速开始)
- [架构](#架构)
- [目录结构](#目录结构)
- [文档](#文档)

## 是什么

一键切换待评测 Agent。让 Agent 学会自动评测。在 Hub 上分享与复用。

- **一键切换待评测 Agent。** 为运行基座按需编写、安装插件，补上你的自定义能力。默认 [ACP](https://agentclientprotocol.com)（[pi](https://pi.dev)、[Codex](https://github.com/openai/codex)、[Claude Code](https://github.com/anthropics/claude-code)、[OpenCode](https://github.com/sst/opencode)）；[nooa](https://github.com/NVIDIA-NeMo/labs-OO-Agents)、[dsh](https://github.com/deepseek-ai/deepseek-harness)、[miniswe](https://github.com/SWE-agent/mini-swe-agent) 同样经插件进来。
- **让 Agent 学会自动评测。** 装上 CLI 和 skill，让 Agent 能设计、转化 benchmark，并自动跑评测。
- **在 Hub 上分享与复用。** 在 ageval Hub 上分享或复用 dataset、插件和 Agent 配置，并上传评测结果。
- **交付单位是 dataset。** 一份 dataset 含若干 task；环境和 Agent 写在 `profiles.yaml` 里，不写进 dataset。

## 如何运行

```text
            你 ── lock / run ──►  ┌─────────────────┐
                                  │    一次运行     │  lock dataset · digest
                                  │   ageval Core   │  environment → run
                                  │                 │  evaluate → record
                                  │                 │  finally cleanup
                                  └────────┬────────┘
                                           │ 打开一个环境
              ┌────────────────────────────┼────────────────────────────┐
              ▼                            ▼                            ▼
        ┌───────────┐                ┌───────────┐                ┌───────────┐
        │   local   │                │  docker   │                │ e2b/ssh/daytona │
        └─────┬─────┘                └─────┬─────┘                └─────┬─────┘
              └──────── Protocol: upload · exec · attach_stdio ─────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │     run.py      │  任务循环 · 调用 Agent
                                  │  ACP / plugin   │  插件接入
                                  └────────┬────────┘
                                           ▼
                                  ┌─────────────────┐
                                  │  evaluator.py   │  PASS 的唯一来源
                                  └─────────────────┘
```

1. **lock。** 把 dataset、环境和 Agent 合成 digest。密钥只当 locator，不以明文写入 lock。
2. **打开环境。** 本机、Docker，或云沙箱 / 远端。缺能力或缺凭证时，在打开之前失败。
3. **跑 `run.py`。** 循环、工具与 Agent 调用写在这里。换环境或 Agent 不用改这份文件。
4. **独立评分。** gold 在这个阶段进入环境，由 `evaluator.py` 给出 PASS / FAIL / ERROR。cleanup 始终执行。

## 功能

**一键切换待评测 Agent**

为运行基座按需编写、安装插件，补上你的自定义能力。环境和 Agent 运行时经插件接入，不用 fork 框架、不用改基座。默认 [ACP](https://agentclientprotocol.com)；[nooa](https://github.com/NVIDIA-NeMo/labs-OO-Agents)、[dsh](https://github.com/deepseek-ai/deepseek-harness)、[miniswe](https://github.com/SWE-agent/mini-swe-agent) 同样走插件。Agent 包 format `ageval.agent/1`；内置包用 `--agent pi`（不必 install），定制包先 `ageval agent install`。

**让 Agent 学会自动评测**

装上 CLI 和 skill，让 Agent 能设计、转化 benchmark，并自动跑评测。`uv tool install ageval-cli`，再 `npx skills add ZJU-REAL/ageval`。

**在 Hub 上分享与复用**

在 ageval Hub 上分享或复用 dataset、插件和 Agent 配置，并上传评测结果。组织管理成员、公开范围与版本。部署可用 `docker compose -f services/registry/docker-compose.yml up -d`。本机 Viewer 按 Jobs → Tasks 打开一次运行。

## 快速开始

从 PyPI 直接安装 CLI。需要 CPython **3.12+**。实际运行 coding agent 还需要本机 ACP 入口与凭据。仅执行 `ageval lock` 时不需要。

```bash
uv tool install ageval-cli
ageval -V
```

可选后端以 extras 提供：`e2b`、`daytona`、`registry`、`nooa`、`dsh`、`miniswe`——或一次装全：

```bash
uv tool install 'ageval-cli[all]'
```

用 registry ref（`<dataset_id>@<version>`）直接跑 Hub 上的 dataset，或跑任意本地 dataset 根目录：

```bash
ageval registry list                        # 查看 Hub 上可见的 dataset
ageval run <org>/<name>@<version> --task <task-id>
ageval executors -v
ageval view <org>/<name>@<version> --no-browser
```

默认 profiles 使用 `environment: docker`（需要可用的 Docker 引擎）。内置 Agent 包用 `--agent pi`（不必 install）。可选 `--model` 改这次 run。定制 overlays 包先 `ageval agent install`，再 `--agent org/name@version`。缺 extras 或凭据时检查不过就不能进入运行，报错里带准确的安装命令。

给你本机 coding agent 用的技能（CLI、插件、dataset 编写、`run.py`/SDK）：

```bash
npx skills add ZJU-REAL/ageval
```

### 从源码开发

仓库内示例——[`examples/README.md`](examples/README.md)：`minimal-demo`、五题缩略的 `tau3-airline-5`，以及 Agent 目录包——需要 clone 仓库：

```bash
git clone https://github.com/ZJU-REAL/ageval.git
cd ageval
uv sync --frozen --all-packages
uv run ageval -V
```

```bash
uv run ageval tasks examples/datasets/minimal-demo
uv run ageval lock examples/datasets/minimal-demo --task terminal-jsonl-agg
uv run ageval run  examples/datasets/minimal-demo --task terminal-jsonl-agg
uv run ageval run  examples/datasets/minimal-demo --task terminal-jsonl-agg --probe
uv run ageval view examples/datasets/minimal-demo --no-browser
```

## 架构

```text
  ageval.yaml + task.yaml + profiles.yaml
                 │
                 ▼
           ageval lock                 digest · extension_bindings
                 │
                 ▼
           ageval run  ── 一次运行 ── environment → run → evaluate → record
                 │                      finally cleanup
                 ▼
        .ageval/runs/<id>/             lock.json · result.json · trajectory.jsonl
                 │
      ┌──────────┼──────────┐
      ▼                     ▼
 ageval view          Registry / Hub
 本机 Jobs            publish · upload-suite · Leaderboard
```

- lock 是规范入口：未知 format 一次失败。插件改的是绑定，不重排 environment → run → evaluate → record 这几个阶段。
- 一次运行管身份、时限、cleanup 与出分。
- 本机 Viewer 读文件；Hub 连 Registry。

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
│   ├── attempt/                     # 一次运行的流水线
│   │   ├── __init__.py              # run_attempt
│   │   └── phases/                  # environment → run → evaluate → record · cleanup
│   ├── config/                      # dataset + task.yaml + profiles
│   ├── environments/protocol.py     # EnvironmentProvider · 能力；不含厂商 SDK
│   ├── plugins/
│   │   ├── slots.py                 # exclusive / chain
│   │   └── contrib/                 # acp · local · docker · e2b · daytona · ssh
│   ├── runtime/                     # 身份、父进程 Agent Service、task_worker
│   ├── evaluation/                  # 绑定 PASS
│   └── evidence/                    # trajectory.jsonl 布局
├── src/ageval_sdk/                  # run.py 用的 ageval_sdk（不判定 PASS，不持有宿主凭据）
├── plugins/                         # 外置 ageval.plugin/1（nooa、dsh、miniswe 等）
├── examples/
│   ├── datasets/
│   │   ├── minimal-demo/            # terminal-jsonl-agg · tau2-dialog-min · multiagent-env-min
│   │   └── tau3-airline-5/            # airline-00 … airline-04
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
