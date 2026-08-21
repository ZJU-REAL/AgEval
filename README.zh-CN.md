# ageval

**agent eval** — 锁定 dataset，选定环境，跑题，由独立 evaluator 出分。

[English](README.md)

[![Release](https://img.shields.io/github/v/release/ZJU-REAL/ageval?display_name=tag&sort=semver)](https://github.com/ZJU-REAL/ageval/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)

Agent 评测常只给模型打分，把编排、隔离、可见性和打分权威留给各家私有栈。换 coding agent 或换环境，分数就不可比。

**ageval** 是这层外层运行时：锁定配置、按边界跑 Attempt、控制可见面，PASS 只来自独立 evaluator。Coding agent 走 **ACP**。其它机制以 `ageval.plugin/1` 安装，再由 job profiles 绑定。环境是独占槽：`local` / `docker` / `e2b` / `ssh`。

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
                                  │     run.py      │  题内 loop · 调 Agent
                                  │  ACP / plugin   │  executor 独占槽
                                  └────────┬────────┘
                                           ▼
                                  ┌─────────────────┐
                                  │  evaluator.py   │  PASS 的唯一来源
                                  └─────────────────┘
```

换环境或换 Agent，题包 `run.py` 不用改。

### 能做什么

- 装上仓内 skill，让 coding agent 选例子、跑 `ageval run`、读结果
- 同一份 `run.py`，用 profiles 换 ACP entry，或绑定 nooa / dsh / miniswe
- `ageval plugin install` 只装本机；install 永不改写 dataset
- 整份 dataset（省略 `--task`）或 campaign 矩阵
- `ageval view` 看本机 Jobs
- 发到 Registry / Hub；公开榜只收完备且绑定 release 的 suite
- `ageval evidence` 导出轨迹

## 快速开始

需要 [uv](https://docs.astral.sh/uv/) 与 CPython **3.12+**。

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

`examples/journeys` 默认环境是 docker。`--probe` 只 lock + preflight。缺 `E2B_API_KEY` / SSH locator 一次失败。

`--profiles` 整份替换 job 文档。`--agent` 与 `--profiles` 互斥。

## 文档

- 设计：[docs/](docs/README.md)
- 用法：[website/](website/)
- 示例：[examples/README.md](examples/README.md)
- [AGENTS.md](AGENTS.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
