# BORA

**Bounded Orchestration for Runtime Agents**（运行时 Agent 的有界编排）

[English](README.md)

[![Release](https://img.shields.io/github/v/release/ffy6511/BORA?display_name=tag&sort=semver)](https://github.com/ffy6511/BORA/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![Issues](https://img.shields.io/github/issues/ffy6511/BORA)](https://github.com/ffy6511/BORA/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/ffy6511/BORA)](https://github.com/ffy6511/BORA/pulls)

---

主流 Agent Benchmark 往往只给模型打分，却把 **Harness**（编排、隔离、可见面、评测边界）留给各家私有实现。换 coding agent、换隔离方式或换上游 Framework，分数很难对齐，复现与轨迹也各自为政。

**BORA** 是这层外层运行时：把 task 配置锁定、按边界跑 Attempt、控制 agent 能看见什么，再由独立 evaluator 出分。Coding agent 统一走 **ACP**，可接入支持该协议的主流 harness 做测评。

### 你能用它做什么

- **用 agent + skill 自动跑测评** — clone 后装上仓库自带 skill，让 coding agent 帮你选 example、执行 `bora run`、读结果与轨迹，少写样板脚本
- **Harness × Agent × Model 自由组合** — 同一套 task harness 通过 ACP 换 Codex / Claude / Pi / OpenCode 等入口与模型，做接近笛卡尔积式的对比评测，而不是为每家后端写一套 scraper
- **把已有 harness 接到统一边界** — 保留你自己的 workflow，外层统一锁定配置、隔离（本机 / Docker）、可见性与独立打分，便于跨框架复现
- **整份 Dataset 或参数矩阵批量跑** — 一次跑完套件内多个 task，或用 campaign 扫 seed / profile 等允许覆盖的参数
- **Suite 聚合分与 job 结果归档** — suite 跑完写入观测用的 `pass_rate` / `mean_score`；需要共享时可以上传到 Registry
- **本机浏览 suite 跑次** — `bora view` 打开 Jobs → Tasks → Attempt；可钻进 run 看 Trajectory、多角色 Time/Usage 与 provenance 外链
- **用 Registry / Hub 共享包与结果** — 按组织发布 Dataset、邀请成员、分享私有结果；已上传的远程 Jobs 可在 Hub 里浏览
- **复盘与导出轨迹** — 每次 invoke 落盘证据；需要时 `bora evidence` 导出，供失败分析或训练管线

---

## 快速开始

需要 [uv](https://docs.astral.sh/uv/) 与 CPython **3.12+**。

```bash
git clone https://github.com/ffy6511/BORA.git
cd BORA
uv sync --frozen --all-packages
uv run bora -V
```

### 常用 CLI

```bash
# 列出 Dataset 内 task
uv run bora tasks examples/core

# 仅锁定配置（不启 agent / evaluator）
uv run bora lock examples/core --task config-minimal

# 真实多轮 agent 路径（需本机 ACP entry 就绪 + 凭证）
uv run bora run examples/core --task sdk-agent-session

# 用 allowlisted 覆盖切换 coding-agent entry
uv run bora run examples/core --task builtin-executor-conformance \
  --set '/parameters/active_profile="pi-mini"'

# 整份 Dataset suite（省略 --task）
uv run bora run examples/core --max-concurrent-tasks 2

# 本机结果台（SPA 先构建一次：cd apps/viewer && pnpm build）
uv run bora view examples/core --no-browser

# 查看本机支持的 executor / ACP entry
uv run bora executors -v
```

### 让 coding agent 帮你跑

[`skills/`](skills/) 经 [`.agents/skills`](.agents/skills) 可被发现。把 skill 交给 agent，让它跑 `examples/` 里的 Dataset；或自己改 `harness.py`。

| Skill                                                | 场景                     |
| ---------------------------------------------------- | ------------------------ |
| [`bora-platform`](skills/bora-platform/)             | 产品地图与红线           |
| [`bora-cli`](skills/bora-cli/)                       | CLI 与结果解读           |
| [`bora-config-package`](skills/bora-config-package/) | 编写 Dataset / task 配置 |
| [`bora-sdk-harness`](skills/bora-sdk-harness/)       | 用 `bora_sdk` 写 harness |

---

## Package 怎么读

**Dataset** 是交付单位：根目录 `bora.yaml` + 成员 task。

```text
examples/core/                    # 一个 Dataset
├── bora.yaml                     # 套件元数据、tasks 根
└── tasks/
    └── sdk-agent-session/
        ├── task.yaml             # harness、provider、agent_profiles、limits、evaluation
        ├── harness.py            # Attempt 内 workflow
        ├── evaluator.py          # 独立 PASS/FAIL
        └── …
```

| 路径                                       | 用途                                     |
| ------------------------------------------ | ---------------------------------------- |
| [`examples/core/`](examples/core/)         | Core 烟测                                |
| [`examples/journeys/`](examples/journeys/) | 案例演示（env / 多 agent / 对话 / 终端） |
| [`examples/l1/`](examples/l1/)             | Docker L1 探针                           |

CLI 指向 **Dataset 根**，`--task <id>` 选成员。列表见 [`examples/README.md`](examples/README.md)。

```yaml
agent_profiles:
  - id: codex-mini
    executor: acp
    options:
      entry: codex # 以 bora executors 为准
    model: gpt-5.4-mini
```

---

## 运行产物怎么读

单 task Attempt 证据在成员目录 `tasks/<task_id>/.bora/runs/<run_id>/`：

```text
tasks/<task_id>/.bora/runs/<run_id>/
├── lock.json              # 锁定配置快照（无 secret）
├── result.json            # 扁平 Result（status、score 等）
├── summary.json
├── harness.json           # harness terminal / 发布事实
├── agent.json
├── effects.jsonl
├── cleanup.json
└── agent/
    ├── events.jsonl
    └── invocations/
        └── 0001-<inv_id>/
            ├── request.json
            ├── final-response.json
            ├── metadata.json
            ├── events.jsonl
            ├── trajectory.jsonl   # turn 级轨迹（有则）
            └── backend_raw/       # 脱敏后的后端流
```

`bora run` stdout 为单个 JSON：`status` / `score` 为评测结果，`logs` 为本次 Attempt 证据根路径。

```bash
uv run bora evidence "$LOGS_PATH" --out /tmp/bora-export
```

**整份 suite**（省略 `--task`）还会在 Dataset 根写入观测聚合：

```text
.bora/suite-runs/<suite_run_id>/summary.json   # metrics.pass_rate / mean_score、task_refs
```

PASS 仍仅 per-task。可选 Registry 归档：`bora results upload-suite`（见 CLI README）。本机 UI：`bora view <dataset>`。

---

## 延伸阅读

| 读者     | 入口                                                         |
| -------- | ------------------------------------------------------------ |
| 设计     | [`docs/design/`](docs/design/)                               |
| 结构     | [`ARCHITECTURE.md`](ARCHITECTURE.md)                         |
| 产品文档 | [`website/`](website/) — 中/英读者向（非设计权威）            |
| CLI      | [`src/bora/cli/README.md`](src/bora/cli/README.md)           |
| Viewer   | [`apps/viewer/README.md`](apps/viewer/README.md) — 本机 SPA 开发 |
| Hub      | [`apps/hub/README.md`](apps/hub/README.md) — Registry SPA 开发 |
| Registry | [`services/registry/README.md`](services/registry/README.md) |
| Issues   | [GitHub Issues](https://github.com/ffy6511/BORA/issues)      |
| 版本     | [Releases](https://github.com/ffy6511/BORA/releases)         |
