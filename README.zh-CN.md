# BORA

**Bounded Orchestration for Runtime Agents**（运行时 Agent 的有界编排）

[English](README.md)

[![Release](https://img.shields.io/github/v/release/ZJU-REAL/BORA?display_name=tag&sort=semver)](https://github.com/ZJU-REAL/BORA/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![Issues](https://img.shields.io/github/issues/ZJU-REAL/BORA)](https://github.com/ZJU-REAL/BORA/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/ZJU-REAL/BORA)](https://github.com/ZJU-REAL/BORA/pulls)

---

主流 Agent Benchmark 往往只给模型打分，却把 **Harness**（编排、隔离、可见面、评测边界）留给各家私有实现。换 coding agent、换隔离方式或换上游 Framework，分数很难对齐，复现与轨迹也各自为政。

**BORA** 是这层外层运行时：把 task 配置锁定、按边界跑 Attempt、控制 agent 能看见什么，再由独立 evaluator 出分。Coding agent 统一走 **ACP**；其它执行机制以 `bora.plugin/1` 安装，再由 job profiles 绑定，不必在 Core 里为每家后端单独解析输出。

### 你能用它做什么

- **用 agent + skill 自动跑测评** — clone 后装上仓库自带 skill，让 coding agent 帮你选 example、执行 `bora run`、读结果与轨迹，少写样板脚本
- **Harness × Agent × Model 自由组合** — 同一套 task harness 通过 ACP 换 Codex / Claude / Pi / OpenCode 等入口与模型，或绑定已安装的机制插件（如 nooa / dsh），做接近笛卡尔积式的对比评测，而不必为每家后端单独解析输出
- **安装机制插件** — `bora plugin install` 装到本机，再在 `profiles.yaml` 里绑定
- **把已有 harness 接到统一边界** — 保留你自己的 workflow，外层统一锁定配置、隔离（本机 / Docker）、可见性与独立打分，便于跨框架复现
- **整份 Dataset 或参数矩阵批量跑** — 一次跑完套件内多个 task，或用 campaign 扫 seed / profile 等允许覆盖的参数
- **Suite 聚合分与 job 结果归档** — suite 跑完写入观测用的 `pass_rate` / `mean_score`；需要共享时可以上传到 Registry
- **本机浏览跑次** — `bora view` 打开 Jobs → Tasks → Attempt，覆盖 suite job 与单题 Attempt；可钻进 run 看 Trajectory、多角色 Time/Usage 与 provenance 外链。Jobs 行可删本机证据树（删 suite 始终级联 Attempt）；CLI 对等 `bora jobs delete --local … --yes`
- **用 Registry / Hub 共享包与结果** — 先上传 Dataset draft 再 `bora release`，或直接发 release；邀请成员、分享私有结果。公开 Leaderboard 只列完备且绑定 release 的 suite；缺题或 draft 绑定行只出现在 Jobs
- **复盘与导出轨迹** — 每次 invoke 落盘证据；需要时 `bora evidence` 导出，供失败分析或训练管线

---

## 快速开始

需要 [uv](https://docs.astral.sh/uv/) 与 CPython **3.12+**。

```bash
git clone https://github.com/ZJU-REAL/BORA.git
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
# 同一 lock 上做本机 / L1 可行性探针（不 invoke、不改 digest）
# uv run bora lock examples/core --task config-minimal --probe

# 真实多轮 agent 路径（需本机 ACP entry 就绪 + 凭证）
uv run bora run examples/core --task sdk-agent-session

# 用 job binding 覆盖切换 coding-agent entry
uv run bora run examples/core --task builtin-executor-conformance \
  --set '/bindings/solver/options/entry="pi"'

# 整份 Dataset suite（省略 --task）
uv run bora run examples/core --max-concurrent-tasks 2

# Always-k：每题 k 次独立 Attempt（仅 CLI/job；用于 pass@k / pass^k）
uv run bora run examples/core -k 5 --max-concurrent-tasks 2
# uv run bora run examples/core --task sdk-agent-session -k 5
# uv run bora run examples/core --resume-suite <suite_run_id> --task sdk-agent-session -k 5
# uv run bora run examples/core --resume-suite <suite_run_id> --task sdk-agent-session --replace-slot

# suite job 控制（可选 --database 读进度 / 写 cancel）
# uv run bora status <suite_run_id> --database examples/core
# uv run bora cancel <suite_run_id> --database examples/core

# 本机结果台（SPA 先构建一次：cd apps/viewer && pnpm build）
uv run bora view examples/core --no-browser
# uv run bora view examples/core --dev --open /jobs/<id>

# 查看本机支持的 executor / ACP entry
uv run bora executors -v

# 机制插件
# uv run bora plugin install plugins/nooa
# uv run bora plugin install plugins/dsh
# uv run bora plugin list

# Dataset draft → 不可变 release（需 Registry 登录 + --org）
# uv run bora publish <dataset> --org <org> --draft
# uv run bora release <org/dataset>
```

### 让 coding agent 帮你跑

[`skills/`](skills/) 经 [`.agents/skills`](.agents/skills) 可被发现。把 skill 交给 agent，让它跑 `examples/` 里的 Dataset；或自己改 `harness.py`。

| Skill                                                | 场景                     |
| ---------------------------------------------------- | ------------------------ |
| [`bora-platform`](skills/bora-platform/)             | 产品地图与红线           |
| [`bora-cli`](skills/bora-cli/)                       | CLI 与结果解读           |
| [`bora-plugin`](skills/bora-plugin/)                 | 编写 `bora.plugin/1`     |
| [`bora-config-package`](skills/bora-config-package/) | 编写 Dataset / task 配置 |
| [`bora-sdk-harness`](skills/bora-sdk-harness/)       | 用 `bora_sdk` 写 harness |

---

## Package 怎么读

**Dataset** 是交付单位：根目录 `bora.yaml` + 成员 task。

```text
examples/core/                    # 一个 Dataset
├── bora.yaml                     # 套件元数据、tasks 根
├── profiles.yaml                 # job binding（role → entry/model）
├── env.example                   # 仅 credential locator 名
└── tasks/
    └── sdk-agent-session/
        ├── task.yaml             # 角色槽 + intent（无 entry/model）
        ├── harness.py            # Attempt 内 workflow
        ├── evaluator.py          # 独立 PASS/FAIL
        └── …
```

| 路径                                               | 用途                                     |
| -------------------------------------------------- | ---------------------------------------- |
| [`examples/core/`](examples/core/)                 | Core 烟测                                |
| [`examples/journeys/`](examples/journeys/)         | 案例演示（env / 多 agent / 对话 / 终端） |
| [`examples/l1/`](examples/l1/)                     | Docker L1 探针                           |
| [`examples/tau3-airline/`](examples/tau3-airline/) | τ³-bench airline 转换包                  |

CLI 指向 **Dataset 根**，`--task <id>` 选成员。完整说明见 [`examples/README.md`](examples/README.md)。

```yaml
# task.yaml — 仅角色槽
agent_profiles:
  - id: solver

# Database profiles.yaml — job binding
# format: bora.profiles/1
# bindings:
#   solver:
#     executor: acp
#     extensions:
#       - plugin: acp
#         options: { entry: codex }  # 以 bora executors 为准
#     model: gpt-5.4-mini
```

---

## 运行产物怎么读

Attempt 证据在 Dataset 根下 `.bora/runs/<run_id>/`：

```text
.bora/runs/<run_id>/
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

`bora run` stdout 为单个 JSON：`status` / `score` 为评测结果，`logs` 为相对 Dataset 根的路径（`.bora/runs/<run_id>`）。

```bash
uv run bora evidence <dataset>/.bora/runs/<run_id> --out /tmp/bora-export
```

**整份 suite**（省略 `--task`），或单 task 且 `-k` / `--n-attempts` > 1，会在 Dataset 根写入 suite job：

```text
.bora/suite-runs/<suite_run_id>/
├── summary.json     # metrics.pass_rate / mean_score / pass_at_k / pass_power_k、task_refs
├── progress.json    # 多 unit 进度
└── cancel.requested # suite cancel 后出现
```

| 指标                         | 作用                                                             |
| ---------------------------- | ---------------------------------------------------------------- |
| `pass_rate` / `mean_score`   | 观测扫一眼                                                       |
| `pass_at_k` / `pass_power_k` | Always-k 后的 job 统计（按 task 取 mean）；**不是** package 身份 |
| `n_attempts`                 | 本次 job 的 k 预算                                               |

PASS 仍仅 **per-task**。`n_attempts` **只走 CLI/job**（不进 `task.yaml` / fingerprint）。Attempt `result.json` 可含 `phase_timing`。可选 Registry 归档：`bora results upload-suite`（见 CLI README）。本机 UI：`bora view <dataset>`（Attempt 页 Timing / Tokens）。

---

## 延伸阅读

| 读者     | 入口                                                             |
| -------- | ---------------------------------------------------------------- |
| 设计     | [`docs/design/`](docs/design/)                                   |
| 结构     | [`ARCHITECTURE.md`](ARCHITECTURE.md)                             |
| 产品文档 | [`website/`](website/) — 中/英读者向（非设计权威）               |
| CLI      | [`src/bora/cli/README.md`](src/bora/cli/README.md)               |
| Viewer   | [`apps/viewer/README.md`](apps/viewer/README.md) — 本机 SPA 开发 |
| Hub      | [`apps/hub/README.md`](apps/hub/README.md) — Registry SPA 开发   |
| Registry | [`services/registry/README.md`](services/registry/README.md)     |
| Issues   | [GitHub Issues](https://github.com/ZJU-REAL/BORA/issues)         |
| 版本     | [Releases](https://github.com/ZJU-REAL/BORA/releases)            |
