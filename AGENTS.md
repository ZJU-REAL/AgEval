# BORA Agent 指令

本文件是仓库级 **Agent / 贡献者路由**：说明读什么、谁说了算、当前事实、不可违反的边界，以及如何交付与校验。  
机制设计正文在 [`docs/design/`](docs/design/)；结构地图在 [`ARCHITECTURE.md`](ARCHITECTURE.md)；版本验收在 [`specs/ROADMAP.md`](specs/ROADMAP.md)。

## 产品名

| 项 | 值 |
| --- | --- |
| 全称 | **Bounded Orchestration for Runtime Agents** |
| 简称 | **BORA** |
| 代际 | v2 greenfield（不兼容归档 v1） |
| 归档 v1 旧称 | Benchmark Orchestration Runtime Architecture |
| v1 只读参考 | 本机 `Developer/Archived/bora-v1`（勿 import、勿假设 API 兼容） |

## 必读顺序

修改代码、契约或 Specs 前，**按序**阅读：

1. [ARCHITECTURE.md](ARCHITECTURE.md) — 当前/目标结构、模块所有权、依赖方向、生命周期与数据流  
2. [docs/README.md](docs/README.md) 与本次相关的 [docs/design/](docs/design/) — **设计权威（自包含）**  
3. [docs/PRD.md](docs/PRD.md) — 产品规格与非目标  
4. [specs/AGENTS.md](specs/AGENTS.md) — Specs 工作区局部规则  
5. [specs/ROADMAP.md](specs/ROADMAP.md) — 按 BORA Core / Harness Core 的交付与验收  
6. `specs/active/` 下与当前工作相关的 Active Spec（含 Decision Summary）  
7. 若存在：`specs/constitution/` 中**用户指定**的实现期决策（可为空）  
8. 实施或修复 Active Spec 时：[specs/BLOCKED.md](specs/BLOCKED.md)  

通用 Spec 模板、螺旋交付细节、完成清单见已安装 skill **`$spec-driven-delivery`** 及其 `references/`。本仓库**不**把完整设计写进 constitution。

## 权威顺序（本仓库特例）

```text
docs/（PRD + design/*）     ← 产品与机制设计权威；自包含，不依赖 vault
  → ARCHITECTURE.md         ← 实现结构权威（当前 vs 目标、所有权、依赖）
  → specs/ROADMAP.md        ← Core 表面交付与版本验收勾选
  → Active Spec             ← 单一实现增量、Phase、证据
  → 公开 smoke / 代码 / 测试 / evidence

specs/constitution/（可选）
  → 仅承载「实现过程中用户明确要求固化」的决策
  → 不得替代 docs 设计，不得复制 design 长文

specs/BLOCKED.md
  → 执行期意外决策审计；低于以上权威；不能单独改产品语义
```

### 冲突处理

1. 停止冲突实现。  
2. 判断是设计变更、结构变更、版本范围变更还是实现偏差。  
3. **先改最高权威 artifact**（设计 → `docs/`；结构 → Architecture；版本验收 → Roadmap；增量 → Active Spec）。  
4. 同一变更内同步下游（README、对方 AGENTS、测试、证据声明）。  

### 与通用 SDD 默认链的差异

通用 skill 常把 Constitution 放在最顶。**本仓设计已定稿在 `docs/`**；Constitution 降为可选的实现期决策日志。  
通用 skill 把 `docs/` 称为 reference authority——在本仓，`docs/design/` **同时是机制规格的单一维护面**；`ARCHITECTURE.md` 仍是**结构事实**的单一维护面（模块树/依赖，不写产品长文）。

## 当前事实

| 项 | 状态 |
| --- | --- |
| 设计 | `docs/design/00`–`10` 已自包含迁入；日常**不**再以 vault 为权威 |
| production 源码 | Config→Lifecycle→L0 Provider→Capability→task worker→parent Agent Service（§8.9 evidence）→`bora run`/`bora campaign`→SDK；`src/bora/evidence/`；terminal L1 / env / campaign **部分切片** |
| 公开 entrypoint | `bora lock` / `bora run` / `bora campaign`（CLI 已暴露；`bora run` 输出 `logs` locator） |
| 证据等级 | **限定 `runnable-mvp`（L0）**：含 `examples/core/attempt-trajectory`（Codex multi-invoke 轨迹树）；其余 core/journeys 见 [examples/README.md](examples/README.md)；**不得**扩写全 suite `isolated` |
| Roadmap | Version Index：**`v0.1`–`v0.18` 已勾**；**`v0.19` ACP 未勾** |
| 活动 Spec | `specs/active/00`–`19`；12–18 completed；**19 ACP**（planning gate open，未授权 `src/`） |
| Constitution 条目 | 含 critic-checkbox-authority、core-not-bench-adapters、L1 multi-agent isolation、**ACP unification draft** |


**禁止**从文档存在、Active Spec 存在、`bora lock` 成功或设计示意推导 `runnable-mvp` / `isolated` / `real-benchmark-verified`。

## 项目边界（Agent 不可违反）

### 架构与所有权

- **BORA Core（五组）：** Config `load_and_lock`；Run/Trial/Attempt 生命周期；Provider 与物理隔离；Capability API；Evaluator barrier 与结果绑定。  
- **可见性投影**是一等能力（workspace path / secret / network / params / artifact materialize）；gold 与 evaluator-only 靠 **不 mount + 评测前 materialize**，禁止只靠「配置里删字段」。  
- **Harness（package）** 拥有 Attempt 内业务 workflow（loop、角色、本地 Tool 组合、handoff 数据）。  
- **Harness Core（SDK）** 可选；可被 upstream Framework 替代；**不**拥有 Run identity、Provider 控制、credential、final PASS。  
- Control Plane **不** import/execute task-local harness 或 evaluator **模块**；经进程/适配器边界调用。  
- 具体平台对象只在 **production composition root**（计划：`application` 内 bootstrap）连接。  
- 第三方 Agent/workflow SDK 不得成为 Core identity / effect / verdict authority。  

### 安全与评测

- `HarnessTerminal.completed` **≠** PASS；PASS 只能来自独立 evaluator。  
- Runtime outcome、Agent 结果、evaluator raw、最终 evaluation 保持为**独立事实**。  
- 不复制、序列化或把 host credential / token 写入 lock、evidence 或 Harness 默认环境；仅 scoped projection 给获准 Adapter/进程。  
- 硬顶由 Runtime/Provider **执行前**强制；Harness 不可自提。事后 token/cost 默认只作观测。  
- Adapter / 插件按**协议、资源类型或执行机制**命名；**禁止**按 Benchmark / task / domain 名分支。  
- 插件模型 = entry point + 包安装；**不是**开放应用商店。Agent Service 等调度面留主仓。  

### Agent 后端 / ACP（Target — Spec 19）

- Coding-agent **Target inlet**：`executor: acp` + `options.entry`；parent **唯一** ACP JSON-RPC client → `AgentResult` + evidence.
- Vendor 私有格式翻译在 **进程外** ACP entry（Mode 1 shim / Mode 2 原生 / Mode 3 厂商包）；**禁止**在 BORA 内再写第二套 vendor stdout scrape（含 `agent_container` heuristic JSON）。
- **L1 官方基座** `docker/attempt` 在 **build 期** bake-in 最低 **五** entry 的 engine + ACP 入口（Mode 1 **双装**：codex/claude/**pi**+各自 adapter）；禁止 invoke 时 `npm i` / floating `npx`。Python ACP SDK **只在 parent**，不进 Attempt 镜像。
- Pi：官方 registry **`pi-acp`**（npm `pi-acp`，桥 `pi --mode rpc`）纳入最低集；勿与反向桥 `pi-shell-acp` 混淆。
- 权威：`docs/design/05` §8.4.3a、[constitution ACP](specs/constitution/2026-08-04-acp-agent-executor-unification.md)、[Spec 19](specs/active/19-acp-agent-executor-plan.md)、[Issue #3](https://github.com/ffy6511/BORA/issues/3)。**未授权不得改 `src/` / 镜像完成态。**

### Package 与配置

- 每 task 规范配置为 `bora.yaml`；Config Core 是唯一规范读取者。  
- `parameters` 给 Harness（`ctx.params`）；envelope 给 Runtime；禁止 harness 再读第二份「真配置」覆盖 lock。  
- 环境变量只作 locator，不能代替生产机制来源。  

### 交付与证据

- 使用 `$spec-driven-delivery` 管理 Specs 工作区、Active Spec 形态、BLOCKED、校验脚本。  
- Roadmap 以 **已定 Core 表面**稳步交付；**不是**探索式改产品方向。版本号 `v0.x` 是索引；语义以 Core 名与 design 为准。  
- 每个 Active Spec：一个可验证增量、Decision Summary、前置条件闭包、success / expected-failure /（有则）regression、工程门禁。  
- Fixture/mock 只能作自动化回归，**不能**单独充当公开 smoke 或升级证据等级。  
- 独立 Critic **默认关闭**；仅当用户或仓库写明 `Independent review: required` 时成为完成 gate。  
- **仅文档规划**不启动实现、不勾选 Roadmap、不改变 Spec 完成态。  
- 实现期安全可逆的范围内选择：先记 `BLOCKED.md` `resolved-autonomously` 再继续；需新权限/不可逆/改产品安全语义时 `awaiting-user`。  
- **禁止**经 `docs/reference/` 软链接**写入** vault 文件。  

## 交付规则（操作）

| 情况 | 做什么 |
| --- | --- |
| 改产品/机制设计 | 先改 `docs/design/*`（及必要时 PRD/glossary），再改 Architecture/Roadmap/Spec/代码 |
| 改模块树/依赖/composition root | 先改 [ARCHITECTURE.md](ARCHITECTURE.md) |
| 改版本结果或验收 | 先改 [specs/ROADMAP.md](specs/ROADMAP.md) |
| 实现一个增量 | 只在所属 Active Spec 内推进 Phase；**边做边勾选** Decision Summary / Phase / AC / gates；末 Phase 同步 docs/README/Architecture/Roadmap |
| Critic 通过 | **立即**勾选对应 Spec 完成项与（条件满足时）Roadmap 关键交付/验收/Version Index；**无需**再等用户验收（见 [specs/constitution/2026-08-03-critic-checkbox-authority.md](specs/constitution/2026-08-03-critic-checkbox-authority.md)） |
| Critic 不通过 | 不得勾选；修代码或诚实回退勾选并记差距 |
| 用户点名固化一条实现决策 | 新建 `specs/constitution/YYYY-MM-DD-<topic>.md`，并链回 docs 相关节 |
| 未授权实现 | **不**创建 `src/` / 不跑「假装完成」的 smoke 声明 |

`specs/active/` **不设数量上限**。依赖只约束实施与完成顺序，不阻止提前写好已确认的后续 Spec。

跟踪 Markdown 使用**仓库相对链接**。不要在 AGENTS/Architecture 里写死仅本机可用的绝对路径作为权威链接（归档路径可用文字说明）。

## 证据等级

| 等级 | 含义 | 何时可声称 |
| --- | --- | --- |
| `design-only` | 仅文档/Specs | 被限定 `runnable-mvp` 覆盖的 journey 之外仍适用 |
| `runnable-mvp` | 真实 public entrypoint + 真实 Agent 路径 | **当前（L0）**：`sdk-agent-session` multi-invoke、`agent-eval`、tool-guard、env/multiagent/tau2 类；Version Index **`v0.7` 已勾** |
| `isolated` | 隔离 Attempt + 隔离红线 | 通常 `v0.8` 类验收后 |
| `real-benchmark-verified` | 固定 upstream + 限定范围公开 journey | 对应 APP/版本验收后；不得扩写成全 suite |

## 校验

从仓库根目录：

```bash
python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict
git diff --check
```

实现开始后，还须运行所属 Active Spec 规定的：frozen install、Ruff、Pyright、pytest、公开 success/expected-failure smoke，以及文档同步检查。

Skill 路径若本机不同，以已安装的 `spec-driven-delivery` 包内 `scripts/validate_specs_workspace.py` 为准。

## 相关入口

| 文档 | 用途 |
| --- | --- |
| [`.agents/skills/`](.agents/skills/) → [`skills/`](skills/) | clone 后可发现的 coding agent Skills（bora-platform / cli / config-package / sdk-harness） |
| [README.md](README.md) | 人类入口与状态 |
| [docs/design/01-bora-core.md](docs/design/01-bora-core.md) | Core 五组 |
| [docs/design/09-owner-matrix-and-structure.md](docs/design/09-owner-matrix-and-structure.md) | Owner 矩阵 |
| [specs/ROADMAP.md](specs/ROADMAP.md) | Core 交付顺序 |
