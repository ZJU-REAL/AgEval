# BORA Agent 指令

本文件是仓库级 **Agent / 贡献者路由**：说明读什么、谁说了算、当前事实、不可违反的边界，以及如何交付与校验。  
机制设计正文在 [`docs/design/`](docs/design/)；结构地图在 [`ARCHITECTURE.md`](ARCHITECTURE.md)；增量交付在 **GitHub Issues**。

## 产品名

| 项 | 值 |
| --- | --- |
| 全称 | **Bounded Orchestration for Runtime Agents** |
| 简称 | **BORA** |
| 代际 | v2 greenfield（不兼容归档 v1） |
| 归档 v1 旧称 | Benchmark Orchestration Runtime Architecture |
| v1 只读参考 | 本机 `Developer/Archived/bora-v1`（勿 import、勿假设 API 兼容） |

## 必读顺序

修改代码、契约或公开行为前，**按序**阅读：

1. [ARCHITECTURE.md](ARCHITECTURE.md) — 当前/目标结构、模块所有权、依赖方向、生命周期与数据流  
2. [docs/README.md](docs/README.md) 与本次相关的 [docs/design/](docs/design/) — **设计权威（自包含）**  
3. [docs/PRD.md](docs/PRD.md) — 产品规格与非目标  
4. 相关 **GitHub Issue**（Acceptance / 非目标 / 证据要求）  
5. 代码、测试、`examples/`、公开 smoke  

读者向产品文档在 [`website/`](website/)（可选阅读）；**不**拥有设计真理。

## 权威顺序

```text
docs/（PRD + design/*）     ← 产品与机制设计权威；自包含
  → ARCHITECTURE.md         ← 实现结构权威（当前 vs 目标、所有权、依赖）
  → GitHub Issues           ← 增量交付、讨论与验收跟踪（主轨道）
  → 公开 smoke / 代码 / 测试 / evidence

website/                    ← 读者向产品文档（重写）；不拥有设计真理
apps/* / services/* README  ← SPA / 服务开发细节；非产品教程权威
```

### 冲突处理

1. 停止冲突实现。  
2. 判断是设计变更、结构变更、范围变更还是实现偏差。  
3. **先改最高权威 artifact**（设计 → `docs/`；结构 → Architecture；交付跟踪 → Issue；实现 → 代码）。  
4. 同一变更内同步下游（README、skills、website 相关页、测试、证据声明）。  

### 与历史 SDD 脚手架的关系

仓库**已移除** `specs/`（Active Spec / ROADMAP / constitution / BLOCKED）。  
历史 Git 中仍可查阅；日常**禁止**再新建 Spec 工作区或勾选机。  
设计已定稿在 `docs/`；交付跟踪在 Issues。

## 当前事实

| 项 | 状态 |
| --- | --- |
| 设计 | `docs/design/00`–`10` 已自包含；日常**不**再以 vault 为权威 |
| production 源码 | Config→Lifecycle→L0 Provider→Capability→task worker→parent Agent Service（§8.9 evidence）→`bora run`/`bora campaign`→SDK；`src/bora/plugins/` 扩展注册表 + first-party contrib；外置 `plugins/`（nooa 等）；`src/bora/evidence/`；terminal L1 / env / campaign **部分切片** |
| 公开 entrypoint | `bora lock` / `bora run` / `bora campaign` / `bora view` / `bora evidence` / `bora plugin` 等（以 `bora --help` 为准；`bora run` 输出 `logs` locator） |
| 证据等级 | **限定 `runnable-mvp`（L0）** 及部分 L1 路径；见 [examples/README.md](examples/README.md)；**不得**扩写全 suite `isolated` |
| 交付跟踪 | **GitHub Issues**（无 ROADMAP / Active Spec） |
| 文档站 | [`website/`](website/) 读者向 Fumadocs；机制权威仍在 `docs/` |
| ACP | 产品决策已接受（`executor: acp` + `options.entry`）；余量与 gap 见 Issues（如 #4）；**有站 ≠ 证据升级** |

**禁止**从文档存在、Issue 存在、`bora lock` 成功或设计示意推导 `runnable-mvp` / `isolated` / `real-benchmark-verified`。

## 项目边界（Agent 不可违反）

### 架构与所有权

- **BORA Core（五组）：** Config `load_and_lock`；Run/Trial/Attempt 生命周期；Provider 与物理隔离；Capability API；Evaluator barrier 与结果绑定。  
- **可见性投影**是一等能力（workspace path / secret / network / params / artifact materialize）；gold 与 evaluator-only 靠 **不 mount + 评测前 materialize**，禁止只靠「配置里删字段」。  
- **Harness（package）** 拥有 Attempt 内业务 workflow（loop、角色、本地 Tool 组合、handoff 数据）。  
- **Harness Core（SDK）** 可选；可被 upstream Framework 替代；**不**拥有 Run identity、Provider 控制、credential、final PASS。  
- Control Plane **不** import/execute task-local harness 或 evaluator **模块**；经进程/适配器边界调用。  
- 具体平台对象只在 **production composition root**（`application` 内 bootstrap）连接。  
- 第三方 Agent/workflow SDK 不得成为 Core identity / effect / verdict authority。  

### 安全与评测

- `HarnessTerminal.completed` **≠** PASS；PASS 只能来自独立 evaluator。  
- Runtime outcome、Agent 结果、evaluator raw、最终 evaluation 保持为**独立事实**。  
- 不复制、序列化或把 host credential / token 写入 lock、evidence 或 Harness 默认环境；仅 scoped projection 给获准 Adapter/进程。  
- 硬顶由 Runtime/Provider **执行前**强制；Harness 不可自提。事后 token/cost 默认只作观测。  
- Adapter / 插件按**协议、资源类型或执行机制**命名；**禁止**按 Benchmark / task / domain 名分支。  
- 插件模型 = entry point + 包安装；**不是**开放应用商店。Agent Service 等调度面留主仓。  

### Agent 后端 / ACP

- Coding-agent **Target inlet**：`executor: acp` + `options.entry`；parent **唯一** ACP JSON-RPC client → `AgentResult` + evidence。  
- Vendor 私有格式翻译在 **进程外** ACP entry（Mode 1 shim / Mode 2 原生 / Mode 3 厂商包）；**禁止**在 BORA 内再写第二套 vendor stdout scrape（含 `agent_container` heuristic JSON）。  
- **L1 官方基座** `docker/attempt` 在 **build 期** bake-in 最低 **五** entry 的 engine + ACP 入口（Mode 1 **双装**：codex/claude/**pi**+各自 adapter）；禁止 invoke 时 `npm i` / floating `npx`。Python ACP SDK **只在 parent**，不进 Attempt 镜像。  
- Pi：官方 registry **`pi-acp`**（npm `pi-acp`，桥 `pi --mode rpc`）纳入最低集；勿与反向桥 `pi-shell-acp` 混淆。  
- **可见性**：仍靠 mount + `docker exec -u/-w` + UID/GID。**Permission**：batch 默认 ACP auto-approve，**不**提权、**不**突破未投影路径；evidence 记录 decision。  
- 权威：[`docs/design/05-runtime/agent-service.md`](docs/design/05-runtime/agent-service.md)、[Issue #3](https://github.com/ffy6511/BORA/issues/3)。产品决策已接受；公开冒烟与实现余量以代码与 Issues 为准。  

### L1 多 Agent 调度（绑定约束）

- L1 Agent 路径必须与 L0 相同 SDK 表面：`Agent.session(...).invoke`；**禁止** silent host fallback。  
- YAML 只声明逻辑 isolation（`shared-container` / `container-per-group`、groups、actors、`shared_write`）；container id / UID 等由 Runtime 拥有。  
- 详见 [`docs/design/05-runtime/`](docs/design/05-runtime/) 与 ARCHITECTURE Current。  

### Package 与配置

- 规范交付单位为 Database / Dataset（根 `bora.yaml` / `bora.database/1`）；每 task 规范配置为成员 `task.yaml`；Config Core 是唯一规范读取者。  
- `parameters` 给 Harness（`ctx.params`）；envelope 给 Runtime；禁止 harness 再读第二份「真配置」覆盖 lock。  
- 环境变量只作 locator，不能代替生产机制来源。  

### 交付与证据

- **新工作默认开 GitHub Issue**（写清 Acceptance / 非目标 / 证据）；**不**新建 Active Spec / ROADMAP。  
- Fixture/mock 只能作自动化回归，**不能**单独充当公开 smoke 或升级证据等级。  
- 实现期安全可逆选择可自行推进；需新权限/不可逆/改产品安全语义时先问用户或写在 Issue。  
- **禁止**经 `docs/reference/` 软链接**写入** vault 文件。  
- **有 `website/` ≠** 证据等级升级。  

## 交付规则（操作）

| 情况 | 做什么 |
| --- | --- |
| 改产品/机制设计 | 先改 `docs/design/*`（及必要时 PRD/glossary），再改 Architecture / 代码 / website 相关页 |
| 改模块树/依赖/composition root | 先改 [ARCHITECTURE.md](ARCHITECTURE.md) |
| 增量功能 / 验收跟踪 | 开或更新 **GitHub Issue**；实现与 PR 链 Issue |
| 教人怎么用（CLI / Viewer / Hub） | 更新 [`website/`](website/)；开发细节留在 `apps/*` / `services/*` README |
| 未授权实现 | **不**创建无依据的 production 行为变更 / 不跑「假装完成」的 smoke 声明 |

跟踪 Markdown 使用**仓库相对链接**。不要在 AGENTS/Architecture 里写死仅本机可用的绝对路径作为权威链接（归档路径可用文字说明）。

### 对外文档禁止 Issue 编号痕迹（硬规则）

**读者向 / 对外文档不得出现 GitHub Issue 编号**（如 `#66`、`#59`、`Issue #60`、`Closes #xx` 文案）。

| 适用 | 不适用（可保留 Issue 引用） |
| --- | --- |
| 根 `README.md` / `README.zh-CN.md` | `AGENTS.md`、`ARCHITECTURE.md`（贡献者路由） |
| [`website/`](website/) 全部读者向正文（中/英） | `docs/design/*`、内部 PR/Issue 讨论 |
| `examples/**/README*` 及包内读者向说明 | 实现与 PR 描述里的 `Closes #N`（给 GitHub 跟踪用） |
| 产品站、教程、公开 smoke 叙述 | 测试名 / 代码注释若仅开发者可见（仍宜少写） |

**写法：** 用产品语义写边界（例：「monorepo 只收 tau3-airline；更大 bench 只走 Hub」），**不要**用「#66 交付边界」这类交付跟踪编号当章节标题或正文标记。  
改文档时若发现对外文面有 `#数字` Issue 痕迹，**先删再合**；中英文同步。

## 证据等级

| 等级 | 含义 | 何时可声称 |
| --- | --- | --- |
| `design-only` | 仅文档 | 未被公开 smoke 覆盖的路径 |
| `runnable-mvp` | 真实 public entrypoint + 真实 Agent 路径 | 有对应公开 journey 证据时 |
| `isolated` | 隔离 Attempt + 隔离红线 | 有对应 L1 / 隔离验收证据时 |
| `real-benchmark-verified` | 固定 upstream + 限定范围公开 journey | 有对应验收证据时；不得扩写成全 suite |

## 校验

### 何时跑 CI 门禁（必须强调）

| 操作 | 是否本地先跑通 CI |
| --- | --- |
| **日常本地 commit** | **不需要**每次全量 CI；按改动路径跑对应门禁即可 |
| **`git push`**（尤其推到将合入 `main` 的分支） | **需要**：先本地跑通与 [`.github/workflows/ci.yml`](.github/workflows/ci.yml) 等价的相关 job |
| **开 / 更新 PR**、**发版 / 打 tag / 发布** | **必须**先本地确认会触发的 CI job 会过，再 push / 开 PR / 发版 |

Agent 在协助 push、PR、发版前：**不得**假设「本地能 import」或「只改了文档」就跳过；应按路径跑下面 **CI 等价命令**（或明确说明已跑且通过）。失败则先修再推。

### CI 门禁（path-filtered 并行 job）

| Job | 触发路径（摘要） | 本地等价 |
| --- | --- | --- |
| `python-core` | `src/` `sdk/` `tests/` `examples/` `services/` `docker/` `scripts/` `pyproject.toml` `uv.lock` `VERSION` … | 见下方 Python core |
| `python-registry` | 同上（与 core 并行；仅 `tests/registry`） | `uv sync --frozen --extra registry` + `pytest tests/registry` |
| `viewer-app` | `apps/viewer/**` | `pnpm --dir apps/viewer install --frozen-lockfile && pnpm --dir apps/viewer lint && pnpm --dir apps/viewer build` |
| `hub-app` | `apps/hub/**` | `pnpm --dir apps/hub install --frozen-lockfile && pnpm --dir apps/hub lint && pnpm --dir apps/hub build` |
| `website` | `website/**` | `pnpm --dir website install --frozen-lockfile && pnpm --dir website build` |

`.github/workflows/ci.yml` 变更会重跑全部 job。纯 SPA / 纯 website 变更**不**跑全量 Python。  
**无** Docker L1、**无**真 Agent/API e2e。

#### Python core（`python-core`）

```bash
uv sync --frozen
uv run ruff format --check src tests
uv run ruff check src tests
uv run pyright
export BORA_OFFLINE_AGENT=1 BORA_SKIP_DOCKER=1
export BORA_SKIP_REAL_CODEX=1 BORA_SKIP_REAL_PI=1
export BORA_SKIP_REAL_OPENCODE=1 BORA_SKIP_REAL_ACP=1
uv run pytest \
  --ignore=tests/registry \
  --ignore=tests/e2e \
  --ignore=tests/provider_l1 \
  --ignore=tests/environment \
  --ignore=tests/executors \
  --ignore=tests/acceptance/test_provider_l1_cli.py \
  --ignore=tests/acceptance/test_l1_package_dockerfile.py \
  --ignore=tests/acceptance/test_l1_sdk_single_actor.py \
  --ignore=tests/acceptance/test_l1_multi_agent_scheduling.py \
  --ignore=tests/acceptance/test_l1_multi_agent_expected_failures.py \
  --ignore=tests/acceptance/test_l1_multi_group_memory_context.py \
  --ignore=tests/acceptance/test_builtin_executor_visibility.py \
  --ignore=tests/acceptance/test_builtin_executor_conformance.py \
  --ignore=tests/acceptance/test_hard_ceiling_cli.py \
  --ignore=tests/acceptance/test_attempt_trajectory_cli.py \
  --ignore=tests/acceptance/test_environment_action_denied_cli.py \
  --ignore=tests/acceptance/test_v1_class_packages.py \
  --ignore=tests/runtime/test_trajectory_source_probe.py \
  -q
```

#### Python registry（`python-registry`）

```bash
uv sync --frozen --extra registry
export BORA_OFFLINE_AGENT=1 BORA_SKIP_DOCKER=1
uv run pytest tests/registry -q
```

若改动触及 L1 / 真 Agent 路径，须按 Issue 或相关测试补跑（那些**不**在默认 CI 内）。  
分支保护 required checks 须包含上述 job 名（旧名 `core` 已拆分）。

## 相关入口

| 文档 | 用途 |
| --- | --- |
| [`.agents/skills/`](.agents/skills/) → [`skills/`](skills/) | clone 后可发现的 coding agent Skills（bora-platform / cli / config-package / sdk-harness） |
| [README.md](README.md) | 人类入口与状态 |
| [website/](website/) | 读者向产品文档（中/英） |
| [docs/design/01-bora-core.md](docs/design/01-bora-core.md) | Core 五组 |
| [docs/design/09-owner-matrix-and-structure.md](docs/design/09-owner-matrix-and-structure.md) | Owner 矩阵 |
| [GitHub Issues](https://github.com/ffy6511/BORA/issues) | 增量交付与验收跟踪 |
