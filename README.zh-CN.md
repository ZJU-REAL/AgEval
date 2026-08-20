# ageval

**agent eval** — 锁定 dataset，打开盒子，跑题，由独立 evaluator 出分。

[English](README.md)

[![Release](https://img.shields.io/github/v/release/ZJU-REAL/BORA?display_name=tag&sort=semver)](https://github.com/ZJU-REAL/BORA/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)

GitHub 仓库路径仍是 `ZJU-REAL/BORA`。产品名、CLI、包是 **ageval**。

Agent 评测常只给模型打分，把编排、隔离、可见性和打分权威留给各家私有栈。换 coding agent 或换盒子，分数就不可比。

**ageval** 是这层外层运行时：锁定配置、按边界跑 Attempt、控制可见面，PASS 只来自独立 evaluator。Coding agent 走 **ACP**。其它机制以 `ageval.plugin/1` 安装，再由 job profiles 绑定。盒子是独占槽：`local` / `docker` / `e2b` / `ssh`。

Attempt 流水线在 `src/ageval/attempt/` 里一眼可见。题包作者写 `run.py` 和 `evaluator.py`，不复制编排。

### 能做什么

- 装上仓内 skill，让 coding agent 选例子、跑 `ageval run`、读结果
- 同一份 `run.py`，用 profiles 换 ACP entry，或绑定 nooa / dsh
- `ageval plugin install` 只装本机；install 永不改写 dataset
- 整份 dataset（省略 `--task`）或 campaign 矩阵
- `ageval view` 看本机 Jobs
- 发到 Registry / Hub；公开榜只收完备且绑定 release 的 suite
- `ageval evidence` 导出轨迹——轨迹不是 PASS

## 快速开始

需要 [uv](https://docs.astral.sh/uv/) 与 CPython **3.12+**。

```bash
git clone https://github.com/ZJU-REAL/BORA.git
cd BORA
uv sync --frozen --all-packages
uv run ageval -V
```

```bash
uv run ageval tasks examples/core
uv run ageval lock examples/core --task config-minimal
uv run ageval run  examples/core --task acp-local-min
uv run ageval run  examples/core --task acp-docker-min --profiles examples/core/profiles.docker.yaml
uv run ageval run  examples/journeys --task terminal-jsonl-agg
uv run ageval executors -v
uv run ageval view examples/core --no-browser
```

`--probe` 只 lock + preflight。缺 `E2B_API_KEY` / SSH locator 一次失败。

`--profiles` 整份替换 job 文档。`--agent` 与 `--profiles` 互斥。

## 文档

仓内文档自包含。不必读仓外设计 vault。

- 设计（权威）：[docs/](docs/README.md)
- 用法：[website/](website/)
- 示例：[examples/README.md](examples/README.md)
- 贡献者路由：[AGENTS.md](AGENTS.md)
- 结构地图：[ARCHITECTURE.md](ARCHITECTURE.md)
