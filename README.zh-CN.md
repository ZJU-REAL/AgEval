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

**ageval** 在统一运行基座上用插件切换待评测 Agent；装上 CLI 和 skill，Agent 能设计、转化 benchmark 并自动跑评测；在 Hub 上分享或复用 dataset、插件和 Agent 配置，并上传评测结果。

<p align="center">
  <img src="docs/assets/why-ageval.jpg" alt="N 种环境 × M 种 Agent 运行时：逐个组合需要 N·M 份定制脚手架；ageval 用插件组合环境和 Agent，一份 dataset 到处跑。" width="800">
</p>

## 快速开始

```bash
uv tool install ageval-cli
# 装全依赖或者按需安装
uv tool install 'ageval-cli[all]' # 一次装全
uv tool install 'ageval-cli[e2b]' # 按需装单个 extra

ageval -V
```

直接跑 Hub 上的 dataset，或跑任意本地 dataset 根目录：

```bash
ageval registry list                        # 查看 Hub 上可见的 dataset
ageval run <org>/<name>@<version> --task <task-id>
ageval executors -v
ageval view <org>/<name>@<version> --no-browser
```

### 安装 skills

为本机 coding agent 安装 skills（CLI 使用、插件、dataset 编写等）：

```bash
# 安装全部
npx skills add ZJU-REAL/ageval
# 指定安装
npx skills add ZJU-REAL/ageval --skill ageval-cli
```

### 从源码开发

体验仓库内的 dataset 示例以及 Agent 目录包，或需要从源码构建，clone 仓库：

```bash
git clone https://github.com/ZJU-REAL/ageval.git
cd ageval
uv sync --frozen --all-packages
uv run ageval -V
```

运行仓库内最小示例并在本地查看器查看结果：

```bash
uv run ageval tasks examples/datasets/minimal-demo
uv run ageval run  examples/datasets/minimal-demo --task terminal-jsonl-agg
uv run ageval view examples/datasets/minimal-demo --no-browser
```

## 功能

**快速切换待评测 Agent**

环境和 Agent 运行时都经插件接入，不必修改基座。默认通过 [ACP](https://agentclientprotocol.com) 启动 agent；[nooa](https://github.com/NVIDIA-NeMo/labs-OO-Agents)、[dsh](https://github.com/deepseek-ai/deepseek-harness)、[miniswe](https://github.com/SWE-agent/mini-swe-agent) 的接入走同一条插件路。修改配置文件 `profiles.yaml` 里的一行，或者用 `--agent` 临时指定来切换 agent。

**让 Agent 自己跑评测**

skill 会告诉你的 coding agent 怎么使用 CLI、怎么写 dataset；之后它自己设计或转化 benchmark，端到端跑完评测。参考[快速开始](#快速开始)，完成 CLI 和 skill 的安装。

**在 Hub 上分享与复用**

你可以将 dataset、插件和 Agent 配置与评测结果上传到 ageval Hub，并在 Hub 上组织管理成员、公开 dataset 范围与版本。

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

1. **lock。** 把 dataset、环境和 Agent 定成一份组合。密钥只当 locator，不以明文写入 lock。
2. **打开环境。** 本机、Docker，或云沙箱 / 远端。缺能力或缺凭证时，在打开之前失败。
3. **跑 `run.py`。** 循环、工具与 Agent 调用写在这里。换环境或 Agent 不用改这份文件。
4. **独立评分。** gold 在这个阶段进入环境，由 `evaluator.py` 给出 PASS / FAIL / ERROR。cleanup 始终执行。

从配置文件到结果查看的完整链路：

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
