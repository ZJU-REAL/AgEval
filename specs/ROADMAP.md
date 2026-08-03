# BORA Roadmap — Core 交付计划

整体设计已定稿于 [`docs/design/`](../docs/design/)。本路线图以 **BORA Core** 与 **Harness Core** 表面作为发版单位，按依赖稳步实现；不以探索式螺旋重排产品方向。每个版本仍需形成可独立验证的工程结果，版本号仅用于索引与验收勾选，机制语义以 Core 名称与设计文档为准。

## 维护规则

- 设计变更先改 `docs/design/`，结构变更先改 [`ARCHITECTURE.md`](../ARCHITECTURE.md)，再同步本文件与 Active Spec。
- Version Index 是唯一版本级状态；只有本版关键交付与验收标准**按诚实证据全部满足**，且 **独立 Critic 通过**后勾选。**不需要**再等用户点一次验收（见 [constitution/2026-08-03-critic-checkbox-authority.md](constitution/2026-08-03-critic-checkbox-authority.md)）。Spec Phase/AC/gates 与内部清单必须与实现同步回写，不得积压。
- `v0.1`–`v0.5` 是 Core 工程检查点。它们可以提供 CLI 或集成探针，但不能单独声称 `runnable-mvp`；第一条真实 Agent 产品竖切仍在 `v0.6`。
- 每个 Active Spec 默认只对应一个版本；依赖约束实施与完成顺序，不阻止提前写好后续已确认 Spec。
- 后一版本从前一已验收 Core 基线开始，并回归所有受影响的既有检查点；依赖版本未验收时，后一版本不得实施或完成。
- Adapter 按协议、资源类型或执行机制命名；禁止按 Benchmark、task、domain、role 或业务 action 分支。
- Fixture/mock 只作自动化回归，不能单独证明公开产品路径、真实 Agent、物理隔离或真实 Benchmark。
- `specs/constitution/` 不写完整设计，仅记录用户明确指定的实现期决策。
- v1 的编号、实现与完成态均不继承；归档 v1 只作只读 oracle。

## 依赖总览

```text
Config (v0.1)
  → Lifecycle (v0.2)
      → Provider L0 (v0.3)
          → Capability (v0.4)
              → Harness Core HC-1 (v0.5)
                  → Evaluation + bora run 竖切 (v0.6)
                      → Harness Core HC-2/3 (v0.7)
                          → Provider L1 隔离 (v0.8)
                              → 插件 AgentExecutor (v0.9)
                                  → Environment 资源 (v0.10)
                                      → Campaign/matrix (v0.11)
                                          → 后台/耐久 authority (v0.12，按需)
```

## 版本索引

- [ ] `v0.1` — BORA Core 1：Config（`load_and_lock` + Task Package）
- [ ] `v0.2` — BORA Core 2：Lifecycle（Run / Trial / Attempt）
- [ ] `v0.3` — BORA Core 3：Provider L0
- [ ] `v0.4` — BORA Core 4：Capability API
- [ ] `v0.5` — Harness Core HC-1：entrypoint + `HarnessContext`
- [ ] `v0.6` — BORA Core 5 + APP 竖切：Evaluation 与真实 `bora run`（Codex）
- [x] `v0.7` — Harness Core HC-2/3：`AgentSession` / `ToolSet` / Guard
- [x] `v0.8` — Provider L1：隔离强化（Docker、credential、writer barrier）
- [ ] `v0.9` — 插件化 `AgentExecutor`（第二后端）
- [ ] `v0.10` — Environment Capability 最小真实资源
- [ ] `v0.11` — Campaign / 实验矩阵
- [ ] `v0.12` — 后台控制与耐久 authority（按需）


> **Acceptance packages (2026-08-03):** primary public journeys are `sdk-agent-session`, `terminal-jsonl-agg` (L1), `multiagent-env-min`, `tau2-dialog-min`, `env-postgres-min`, and `bora campaign` matrix — **not** `echo-contract` / ultra-thin toys.

## Core 能力缺口 → v1 同类 case（不是 bench adapter）

**产品目标：** 补齐 **BORA Core / Harness Core** 通用机制，使 *任意* 符合契约的 Task Package 能表达 v1 里那几类能力。  
**不是：** 为 Terminal-Bench / MultiAgentBench 写专用 adapter、专用 Version 名、或按 task 名分支。

| v1 能力形态（oracle 只读） | 需要的 **Core/SDK 表面** | 已有 Roadmap 槽位 | 当前诚实状态 |
| --- | --- | --- | --- |
| 薄 Agent + 独立 evaluator（codex-smoke） | Core 1–5 + Agent Executor + barrier | **v0.6–v0.7** | **可跑**（`agent-eval` + parent-bound `sdk-agent-session` multi-invoke）；仍为 L0 |
| Agent 在 Attempt **workspace 写文件** → seal artifact → 独立评测（terminal 形态） | **Provider 工作区/投影 + Agent cwd/workspace view + file artifact collect + clean evaluator inputs** | **v0.3 L0 + v0.8 L1**（非“v0.13 terminal-bench”） | **terminal-jsonl-agg L1 PASS**（harness+clean eval container, `assurance:l1` when full_l1）；Agent 仍为 parent Executor + workspace-only cwd；Version Index v0.8 未勾 |
| 多步/多角色 Harness + **Attempt-local 有状态资源**（database 形态） | **Agent multi-invoke/channel + Environment Manager + 资源型 Adapter（postgresql）+ Tool 经 Capability** | **v0.7 Session + v0.10 Environment** | **env-postgres-min + multiagent-env-min PASS**（parent-prepared Postgres handoff）；Environment Manager/Capability proxy residual；Version Index v0.10 unchecked |
| 多 Trial 矩阵 / 串行 campaign | Campaign + matrix → Config variant | **v0.11** | **bora campaign seed matrix all_pass + distinct digests**；admission/retry residual；Version Index v0.11 unchecked |
| 多轮 review / budget 负向 | hard ceiling + multi-invoke + 负向 public path | **v0.4/v0.6/v0.7** | 硬顶未在 production run 全闭合 |
| 可选后台/耐久 | ControlStore + supervisor | **v0.12 条件性** | 草图；Research B3 |

### 正确交付顺序（按 Core，不按 bench 名）

1. **收口 Agent authority**（worker→parent channel、hard ceiling、真实 Session 绑定）— Spec 05/06 诚实缺口  
2. **Provider workspace + 文件产物路径**（先 L0 诚实 workdir，再 **v0.8 L1** 物理隔离）— **禁止** TerminalBench* 模块  
3. **Environment Manager + postgresql 接入 `bora run`** — **v0.10**；Adapter 只认资源协议  
4. **Campaign variant→lock** — **v0.11**  
5. 每个 Core 增量后：用 **薄代表 package** 做 public smoke（可 *inspired by* v1 task，但命名用通用 case，如 `workspace-file-agg` / `env-postgres-min`）

### 已作废的错误路线

- ~~v0.13 terminal-bench class~~、~~v0.14 multiagentbench class~~ 作为 Version Index 行：**删除**。  
- 不得新增 `TerminalBenchAdapter` / `MultiAgentBenchAdapter` / 按 task_id 分支。



> **Codex audit + re-verdict 2026-08-02 (delegated review):** Independent audit + post-fix re-verdict conclude **no Version Index row is safe to check yet** (all KEEP_UNCHECKED). B-01 silent PASS paths fixed; real L0 `agent-eval` / `echo-contract` PASS recorded. **Evidence grade may be claimed as narrowly scoped `runnable-mvp` for those L0 journeys only** — excludes AgentSession/L1/plugins/Environment/Campaign/durable/benchmarks. Version Index remains **all unchecked**.


## v0.1 — BORA Core 1：Config

### 目标

Config Core 成为 `bora.yaml` 的唯一规范读取者，并通过可安装 CLI 提供可验证的 `load_and_lock`。

### 起始可运行基线

- Public entrypoint: none。
- Baseline smoke: none；当前只有 `python3 "$HOME/.agents/skills/spec-driven-delivery/scripts/validate_specs_workspace.py" . --strict` 文档门禁。
- Observable result: `design-only` 文档与 Specs；无 production composition root。

### 演进增量

同批建立最小 Python 工程骨架、production CLI composition root、Task Package 定位与 Config Core；本版只交付 Config 表面，不创建 Lifecycle、Provider、Capability、Evaluator 或 Agent 伪实现。

### 设计

- [Config Core](../docs/design/02-task-package-and-config.md#6-core-1-详细设计config)
- [BORA Core 五组机制](../docs/design/01-bora-core.md#22-五组必须保留的-core-机制)
- [Spec 00](active/00-core-batch0-and-batch1-plan.md)

### 关键交付

- [x] 可复现安装、`bora --help` 与 production composition root 可调用。
- [x] Package 一级布局、`bora.yaml` 定位与未知路径策略符合 design/02。
- [x] `load_and_lock` 完成读取、合并、校验、canonicalize、digest 与不可变 lock。
- [x] `bora lock examples/config-minimal --task config-minimal` 输出无 secret 的锁定摘要。
- [x] 非法格式、未知 task、未知 profile、越界路径或不支持 capability 在 Attempt 之前 fail-closed。

### 验收标准

- [x] Success：从 clean checkout 执行 frozen install 后，`uv run bora lock examples/config-minimal --task config-minimal` 返回 0，并输出稳定 `task_id`、format、resolved references 与 digest。
- [x] Expected failure：`uv run bora lock examples/config-invalid --task config-invalid` 返回 2，且不写成功 lock 或伪造后续阶段。
- [x] Determinism：同一输入两次 lock 的 canonical payload 与 digest 相同；合法 override 改变 digest 并进入 resolution record。
- [x] Engineering gates：frozen install、Ruff、Pyright、pytest、strict Specs validator 与 `git diff --check` 全部通过。
- [x] Documentation：README、Architecture Current 树、root/specs AGENTS 当前事实与实际入口同步；证据等级仍为 `design-only`，不得声称 `runnable-mvp`。

> **Version Index `v0.1` 保持未勾选**，直至用户完成最终验收。

### 后续 TODO

- [ ] `v0.2`：在已锁定配置上创建 Run / Trial / Attempt identity 与外层状态顺序。
- [ ] `v0.6`：首次把 Config 检查点接入真实 Agent、Evaluator 与公开产品竖切。

## v0.2 — BORA Core 2：Lifecycle

### 目标

Lifecycle Core 在不启动真实 Harness 的前提下拥有 Run / Trial / Attempt identity、外层状态转移与统一 cleanup 入口。

### 起始可运行基线

- Public entrypoint: `bora lock`。
- Baseline smoke: `uv run bora lock examples/config-minimal --task config-minimal`。
- Observable result: 可复盘 `LockedTaskConfig` 摘要；尚无 Attempt、Harness 或评价结果。

### 演进增量

在 Config 基线上增加独立于 Harness workflow 的 identity、状态机、outcome 与取消/超时收口规则；本版使用 application 级 lifecycle probe 与测试 Adapter 验证顺序，不把内部探针宣传成产品 run。

### 设计

- [Run Coordinator](../docs/design/05-runtime-core.md#82-run-coordinator)
- [运行生命周期](../docs/design/05-runtime-core.md#11-运行生命周期)
- [Core 2](../docs/design/01-bora-core.md#24-core-2runtrial-与-attempt-生命周期)
- [Spec 01](active/01-v0.2-lifecycle-core-plan.md)

### 关键交付

- [x] Run / Trial / Attempt identity 及其不可混用约束。
- [x] `created → preparing → running_harness → harness_terminal → sealing_inputs → evaluating → binding_result → cleaning_up → terminal` 外层状态模型。
- [x] prepare、Harness、evaluation、cleanup 结果保持为独立事实；尚未实现的边界由显式 test double 占位，不进入 production composition。
- [x] retry 创建新 Attempt identity；取消、超时与异常收敛到同一 cleanup 路径。

### 验收标准

- [x] Success：application 集成测试从合法 lock 创建唯一 Run / Trial / Attempt，并按允许顺序到达测试终态。
- [x] Expected failure：非法状态跳转或跨 Attempt identity 复用被拒绝，旧状态与 evidence 不被改写。
- [x] Failure paths：prepare、run、evaluate 任一阶段故障都进入一次有界 cleanup；cleanup warning 不覆盖既有阶段事实。
- [x] Regression：`v0.1` success、expected failure 与 determinism 全部通过。
- [x] Engineering gates：Ruff、Pyright、pytest、strict Specs validator 与 `git diff --check` 通过；Architecture lifecycle Current/Target 描述同步。

> **Version Index `v0.2` 保持未勾选**，直至用户完成最终验收。

### 后续 TODO

- [ ] `v0.3`：用真实 L0 process Provider 替换 lifecycle probe 的运行位置边界。
- [ ] `v0.6`：Evaluator 形成正式 status/score，并把 lifecycle 接入产品 CLI。

## v0.3 — BORA Core 3：Provider L0

### 目标

Provider Core 以真实本地子进程提供 L0 运行位置、最小 workspace 边界、终止与 cleanup，并如实记录 assurance。

### 起始可运行基线

- Public entrypoint: `bora lock`；Lifecycle 通过 application 集成探针验证。
- Baseline smoke: `v0.1` CLI smokes + `v0.2` lifecycle integration suite。
- Observable result: identity 与阶段顺序可验证；尚无真实 Harness 或 product run。

### 演进增量

为单 Attempt 前台执行增加真实 local-process Provider、受限 workdir 与进程终止路径；L0 不承诺 container、per-actor mount、UID/GID、强 network 或 credential 隔离。

### 设计

- [Provider](../docs/design/05-runtime-core.md#83-provider)
- [Provider 与物理隔离](../docs/design/01-bora-core.md#25-core-3provider-与物理隔离)
- [Prompt 与物理隔离](../docs/design/06-capability-adapter-visibility.md#104-prompt-隔离与物理隔离可见性投影)
- [Spec 02](active/02-v0.3-provider-l0-plan.md)

### 关键交付

- [x] `LocalProcessProvider` 或等价机制按 locked workdir 启动真实子进程，并捕获 exit、timeout、cancel 与 stderr 摘要。
- [x] workspace root 与 package root 引用经路径校验；子进程不取得 Docker socket 或未声明宿主控制面。
- [x] timeout / cancel 执行 terminate→bounded wait→kill，并确认 writer 进程已停止。
- [x] evidence 明确记录 `assurance: l0` 与未提供的 L1/L2 保证。

### 验收标准

- [x] Success：Provider integration probe 在 L0 workdir 启动真实子进程、写入允许路径、返回结构化 process outcome 并完成 cleanup。
- [x] Expected failure：越界 workdir 或未声明可执行入口在进程启动前失败，不创建孤儿进程。
- [x] Timeout：超时子进程被终止，后续检测不到持续 writer；cleanup 为幂等。
- [x] Regression：`v0.1` Config 与 `v0.2` lifecycle 全部通过。
- [x] Engineering gates：Ruff、Pyright、pytest、进程/路径集成测试、strict Specs validator 与 `git diff --check` 通过；证据等级不升级为 `isolated`。


> **Version Index `v0.3` 保持未勾选**，直至用户完成最终验收。

### 后续 TODO

- [ ] `v0.4`：向 L0 runtime 注入 Attempt-scoped Capability，并在执行前拒绝越权操作。
- [ ] `v0.8`：Docker、mount、network 与 credential projection 提升到 L1。

## v0.4 — BORA Core 4：Capability API

### 目标

Runtime 向 Attempt 注入受限 Capability，并在 Harness terminal 后关闭能力、在外部效果开始前拒绝未授权请求。

### 起始可运行基线

- Public entrypoint: `bora lock`；Lifecycle 与 L0 Provider 通过集成探针验证。
- Baseline smoke: `v0.1` CLI smokes + `v0.2` lifecycle + `v0.3` Provider L0 suites。
- Observable result: 可启动、终止并清理真实 L0 process；尚未启动 package Harness。

### 演进增量

增加 `params`、`scope`、`agent`、`environment`、`workspace`、`artifacts` 与 `events` 的最小 Attempt-scoped 契约及 production authority；未交付的具体 Agent/Environment 实现必须显式 unavailable，不能用 permissive fake 填充。

### 设计

- [HarnessContext capability 面](../docs/design/01-bora-core.md#26-core-4capability-api)
- [Capability](../docs/design/06-capability-adapter-visibility.md#91-capability)
- [Capability scope](../docs/design/08-conversion-security-testing.md#183-capability-scope)
- [Spec 03](active/03-v0.4-capability-api-plan.md)

### 关键交付

- [x] `HarnessParameterView` 只读投影与 Attempt-scoped `RunScope`。
- [x] Agent、Environment、Workspace、Artifact、Event capability 的统一 open/closed 与 scope 检查。
- [x] `limits.agent_invocations` / `limits.environment_actions` 在受控 effect 前 authorize 或 reject；不支持的 dimension 不伪装成硬顶。
- [x] capability 不可序列化后跨 Attempt 复用，Harness terminal 后调用失败。

### 验收标准

- [x] Success：integration harness client 在同一 Attempt 内读取 params、发布声明 output 并写通用事件，receipt/evidence 绑定正确 identity。
- [x] Expected failure：未声明 artifact/environment action、跨 Attempt capability 或 closed capability 在 Adapter 开始前失败，外部状态保持不变。
- [x] Hard ceiling：以 test-only sink 证明最后一个允许的 Agent/Environment 请求可执行、下一请求在 effect 前拒绝；production 缺少真实 delegate 时保持 unavailable，当前版本只声称进程内单 Attempt authority。
- [x] Regression：`v0.1`–`v0.3` 的所有 acceptance suites 通过。
- [x] Engineering gates：Ruff、Pyright、pytest、negative capability tests、strict Specs validator 与 `git diff --check` 通过；权限/限制措辞与 docs 同步。


> **Version Index `v0.4` 保持未勾选**，直至用户完成最终验收。
>
> **Codex audit honesty v0.4:** 内部勾选为工程进度；Capability 七面合同/named test suites 与 public composition 使用仍有缺口，**不得**据此勾选 Version Index。

### 后续 TODO

- [ ] `v0.5`：把 Capability 通过统一 entrypoint 注入 package Harness。
- [ ] `v0.8`：用 L1 物理投影封闭 L0 无法阻止的 filesystem/network/secret 旁路。
- [ ] `v0.12`：仅在真实并发/reopen 需求出现后评估 durable quota authority。

## v0.5 — Harness Core HC-1：entrypoint 与 Context

### 目标

Runtime 能通过 L0 Provider 启动 package Harness，并向其注入最小 `HarnessContext` 与只读 `ctx.params`。

### 起始可运行基线

- Public entrypoint: `bora lock`；Core 2–4 通过 integration probes 验证。
- Baseline smoke: `v0.1`–`v0.4` 全部 acceptance suites。
- Observable result: Runtime 已拥有 identity、L0 process 与 Capability，但尚无 package Harness 入口闭环。

### 演进增量

交付可选 `bora_sdk` HC-1、task runtime bootstrap 与 `harness:run(ctx)` 调用约定；Control Plane 只启动 task runtime，不 import task-local `harness.py` 模块。

### 设计

- [Harness entrypoint](../docs/design/04-harness-core-sdk.md#71-harness-entrypoint)
- [HarnessContext](../docs/design/04-harness-core-sdk.md#72-harnesscontext)
- [Harness 职责](../docs/design/03-harness-layer.md#31-harness-的职责)
- [Spec 04](active/04-v0.5-harness-core-entrypoint-plan.md)

### 关键交付

- [x] `bora_sdk` 暴露最小 `HarnessContext`、`HarnessParameterView`、`RunScope`、`HarnessTerminal` 与 publish helper。
- [x] task runtime bootstrap 解析 `harness.entrypoint`，在 L0 process 内加载 package code，并注入当前 Attempt capability。
- [x] example harness 从 `ctx.params` 构造 typed params、发布 declared output 并返回 `HarnessTerminal`。
- [x] 缺失入口、错误签名、Harness 异常或 terminal 后 capability 调用形成明确 runtime failure。

### 验收标准

- [x] Success：application integration path 启动 `examples/harness-minimal`，读取 locked params、发布 declared JSON、返回 terminal 并停止 writer。
- [x] Expected failure：缺失/错误 Harness entrypoint 在 evaluator 之前失败并进入 cleanup；Control Plane 未 import package 模块。
- [x] Boundary：Harness 看不到完整 `LockedTaskConfig`、host credential、Docker socket、evaluator-only material 或 final verdict API。
- [x] Regression：`v0.1`–`v0.4` acceptance suites 全部通过。
- [x] Engineering gates：Ruff、Pyright、pytest、process-boundary integration tests、strict Specs validator 与 `git diff --check` 通过；SDK/API 文档同步。


> **Version Index `v0.5` 保持未勾选**，直至用户完成最终验收。
>
> **Codex audit honesty v0.5:** worker 仍接收绝对 package root；Provider start/wait 与 Capability 重建未完全按 Spec 闭合。

### 后续 TODO

- [ ] `v0.6`：接入真实 Codex、独立 Evaluator、扁平 Result 与公开 `bora run`。
- [ ] `v0.7`：增加 `AgentSession`、`ToolSet`、Hook 与 Guard helper。

## v0.6 — BORA Core 5 + 首条 `bora run` 竖切

### 目标

打通独立 Evaluation barrier 与 production CLI，使真实 Codex Harness 通过 `bora run` 产出可区分 runtime/evaluation/cleanup 的 Result 与 evidence。

### 起始可运行基线

- Public entrypoint: `bora lock`；package Harness 已能通过 application integration path 在 L0 运行。
- Baseline smoke: `v0.1`–`v0.5` 全部 acceptance suites。
- Observable result: declared output 与 `HarnessTerminal` 可形成，但没有独立 evaluator verdict 或产品 run 命令。

### 演进增量

交付内置 Codex `AgentExecutor`、Agent Service 最小路径、Evaluator runner、writer barrier、allowlisted input materialization、flat Result、evidence 与 `bora run`；本版只声称 L0 前台单 Attempt，不声称 Docker 隔离或真实 upstream Benchmark 支持。

### 设计

- [Evaluator Runner](../docs/design/05-runtime-core.md#87-evaluator-runner)
- [Result Binder](../docs/design/05-runtime-core.md#88-result-binder)
- [Evaluator barrier](../docs/design/07-budget-evaluation-failure.md#143-evaluator-barrier)
- [Agent Service](../docs/design/05-runtime-core.md#843-agent-serviceruntime)
- [Spec 05](active/05-v0.6-evaluation-app-vertical-slice-plan.md)

### 关键交付

- [ ] `bora run <package> --task <id>` 通过 production composition root 驱动 Core 1–5（CLI 已 `build_run_task()`；完整 lifecycle/authority wiring 仍有缺口 → 保持未勾）。
- [ ] 内置 Codex Executor 使用 Runtime credential binding 与 locked profile；scoped projection + parent pre-effect hard ceiling 未按 Spec 05 全文闭合。
- [ ] Harness terminal 后 close capability、停止 writers、只 materialize `evaluation.inputs`、独立运行 evaluator 并校验 raw output（有独立 evaluator 子进程；full writer barrier spawn-count=0 未全证）。
- [ ] flat Result 分离 `status`、`score`、`metrics`、`error.phase`、`cleanup_warning` 与 evidence locator；whole-tree secret scan 未作正式验收。

### 验收标准

- [x] Success：真实 Codex 公开 journey — 本机已记录 `bora run examples/agent-eval` 与 `examples/echo-contract` exit 0 / PASS / score 1.0 / assurance l0（Codex re-verdict 2026-08-02）；**不**据此勾选 Version Index。
- [x] Expected failure：`uv run bora run examples/agent-eval --task unknown` 在 Agent 调用前返回 2，不创建伪 PASS。
- [x] Evaluator negative control：`uv run bora run examples/evaluator-negative --task evaluator-negative` 完成 Harness 后由独立 evaluator 给出合法 FAIL/低分，证明 `HarnessTerminal.completed` 不等于 PASS。
- [ ] Barrier：缺失 declared output 或未停止 writer 时 evaluator 不启动；cleanup 仍执行且失败只形成 warning（stale-file fail-closed 已证；full writer inventory 未闭合）。
- [ ] Regression：`v0.1`–`v0.5` acceptance suites 全部通过（需每次发版前重跑并记录）。
- [ ] Engineering gates：frozen install、Ruff、Pyright、pytest、公开 smokes、strict Specs validator、`git diff --check` 与文档同步全部通过（需与当前树同批记录）。
- [x] Evidence：Codex 委托复审允许**限定** `runnable-mvp`（仅 L0 `agent-eval` / `echo-contract`）；不得扩写 `isolated` / Version Index。

> **Version Index `v0.6` 保持未勾选**。**Codex re-verdict honesty:** 公开 Success 可勾；关键交付 1–4 与 Barrier/Regression/Engineering 保持 `[ ]`。

### 后续 TODO

- [ ] `v0.7`：Harness Core helper 在同一 `bora run` 路径中复用 Capability，不改变 Core authority。
- [ ] `v0.8`：把公开路径搬到 L1，验证 hidden material、credential 与 writer 的物理隔离。
- [ ] [Benchmark 选型 Research](research/2026-08-02-v1-reference-and-first-benchmark-selection-research.md)：选择首个真实 upstream journey；`v0.6` 不宣称 `real-benchmark-verified`。

## v0.7 — Harness Core HC-2/3：Session、Tool 与 Guard

### 目标

Harness 作者可用 `AgentSession`、`ToolSet`、Hook 与 Guard 减少重复样板，同时 Runtime 继续拥有真实 Agent、外部 effect、hard ceiling 与 final verdict authority。

### 起始可运行基线

- Public entrypoint: `bora lock`、`bora run`。
- Baseline smoke: `v0.6` 真实 Codex success、unknown-task failure、evaluator negative control，以及 `v0.1`–`v0.5` acceptance suites。
- Observable result: L0 前台单 Attempt 已达到限定范围 `runnable-mvp`，Harness 仍直接调用最小 Capability。

### 演进增量

在可选 SDK 内增加 Attempt-bound Agent session、Tool dispatch、before/after hooks、`AllowList`、`CallLimit` 与最小 async workflow helper；业务 Tool、role、branch、router 与 retry 语义继续由 Task Harness 或 upstream Framework 拥有。

### 设计

- [Agent 与 AgentSession](../docs/design/04-harness-core-sdk.md#75-agent-与-agentsession)
- [Tool、Hook 与 Guard](../docs/design/04-harness-core-sdk.md#77-toolhook-与-guard)
- [Tool 上限](../docs/design/04-harness-core-sdk.md#78-tool-上限的配置与执行)
- [Workflow helpers](../docs/design/04-harness-core-sdk.md#79-workflow-helpers)
- [Spec 06](active/06-v0.7-harness-core-session-tool-plan.md)

### 关键交付

- [x] `AgentSession` 由 parent Agent Service（Unix socket）绑定 Attempt + profile；multi-invoke 走同一 hard ceiling；workspace-view 独立 id 为 residual honesty（override kwargs 仍拒绝）。
- [x] `ToolSet` 完成 schema 校验、hook 顺序、callable 调用与 `Observation` 归一化（本地 helper）。
- [x] `AllowList` / `CallLimit` 从 `ctx.params` 构造并在本地 Tool 调用前拒绝（local soft policy only）。
- [x] `bounded_gather` 等 helper 只做进程内组合，不创建第二套 Run/Trial scheduler 或 durable authority。

### 验收标准

- [x] Success：`uv run bora run examples/sdk-agent-session --task sdk-agent-session` 真实 Codex parent-bound multi-invoke（`agent_invocations: 2`）+ independent Evaluator PASS；offline 不静默 PASS；禁止 stub PASS。
- [x] Tool success：`uv run bora run examples/sdk-tool-guard --task sdk-tool-guard` 使用 `ToolSet` 在限额内调用 declared local Tool 并形成可评测 artifact。
- [x] Expected failure（policy denial）：负向 CallLimit package 在 callable 前拒绝（本地 Tool soft policy）。
- [x] Authority regression：parent hard ceiling pre-spawn reserve（unit + production limit=2）；SDK 无 Runtime authority imports。
- [x] Regression：focused + full pytest package green with named e2e/sdk/architecture/security suites。
- [x] Engineering gates：Ruff、Pyright、pytest、SDK contract/negative tests、公开 smokes、strict Specs validator 与 `git diff --check`（见 gate logs）。

> **Critic 2026-08-03 R2+R3:** Spec 06 surfaces closed; R3 **Version Index v0.7 `AUTHORIZE_CHECK`** after honesty + `gates/06-full.log` (ruff/pyright/pytest/validate/git-diff).


> **Version Index `v0.7` checked** (Critic + honesty sync + named suites + gates).

### 后续 TODO

- [ ] `v0.8`：把同一 SDK public path 放入 L1，验证 workspace、credential、network 与 hidden material 的物理边界。
- [ ] `v0.9`：第二 AgentExecutor 必须复用同一 `AgentSession` / `ctx.agent.invoke` 契约，Harness 不按后端分支。
- [ ] `v0.10`：外部业务 Tool 仍由 Harness 组合，但 mutation 只通过 Environment Capability。
- [ ] `v0.12`：只有真实 reopen 需求成立后，才增加 durable session binding；v0.7 的 BORA binding 不可跨 parent process 恢复。

## v0.8 — Provider L1：隔离强化

### 目标

将既有 `bora run` 放入 L1 Attempt，物理强制 workspace、credential、network、hidden material 与 writer barrier。

### 起始可运行基线

- Public entrypoint: `bora run`，L0 前台单 Attempt。
- Baseline smoke: `v0.6` 真实 Codex路径 + `v0.7` SDK examples + 全部早期 Core suites。
- Observable result: `runnable-mvp`；尚无 `isolated` 证据。

### 演进增量

增加 Docker（或等价）Provider、L1 path views、scoped credential projection、network policy、evaluator-only material 分离与 clean evaluator runtime；L2 per-actor UID/GID 不在本版范围。

### 设计

- [Provider](../docs/design/05-runtime-core.md#83-provider)
- [物理可见性投影](../docs/design/06-capability-adapter-visibility.md#104-prompt-隔离与物理隔离可见性投影)
- [安全与信任边界](../docs/design/08-conversion-security-testing.md#18-安全与信任边界)
- [Spec 07](active/07-v0.8-provider-l1-isolation-plan.md)

### 关键交付

> **Critic 2026-08-03:** Full L1 matrix on named packages; Version Index `v0.8` after AUTHORIZE_CHECK. Limited `assurance:l1` — not umbrella `isolated`.

- [x] 隔离 Attempt、明确 image/platform、workspace path views、network 与 credential projection。
- [x] `evaluation/`、gold 与 evaluator-only material 不 mount 给 Harness/Agent，只在 barrier 后 materialize。
- [x] writer stop、timeout/kill 确认与 clean evaluator runtime 形成可重复证据。

### 验收标准

- [x] Success：`provider-l1-agent-eval` + `terminal-jsonl-agg` 真实 Codex L1 PASS 与 `assurance: l1` evidence。
- [x] Expected failure：hidden-material / projection-denied 负向 PASS（fail closed）。
- [x] Writer negative：residual-writer 终止且 evaluator 不启动。
- [x] Regression：pytest package green（含 Spec 06/L0 suites）。
- [x] Evidence：限定 package/platform/image 范围的 `assurance:l1`；**不**扩写 `real-benchmark-verified` / 全 suite `isolated`。

### 后续 TODO

- [ ] `v0.10`：首个有状态 Environment 在同一 Attempt 隔离与 cleanup 中运行。
- [ ] [Benchmark 选型 Research](research/2026-08-02-v1-reference-and-first-benchmark-selection-research.md)：确定首个固定 upstream 与平台 pin。

## v0.9 — 插件化 AgentExecutor

### 目标

操作者可仅改 locked profile 选型切换到第二 AgentExecutor，Task Harness 与 Core authority 不随具体后端变化。

### 起始可运行基线

- Public entrypoint: L1 `bora run` + first-party Codex Executor。
- Baseline smoke: `v0.8` L1 success/negative journeys 与 `v0.1`–`v0.7` regressions。
- Observable result: 单一 Agent 后端可运行；插件发现与跨后端契约尚未证明。

### 演进增量

增加 entry point 发现、profile→executor capability 校验、插件版本记录与第二后端最小真实路径；插件只实现薄 Executor，不取得 Run、credential store、workspace grant 或 evaluator authority。

### 设计

- [可分发插件](../docs/design/05-runtime-core.md#846-扩展模型core-开放接口--可分发插件)
- [AgentExecutor](../docs/design/05-runtime-core.md#847-示例接口agentexecutoragent-扩展面)
- [Adapter 准入](../docs/design/06-capability-adapter-visibility.md#93-adapter-准入)
- [Spec 08](active/08-v0.9-plugin-agent-executor-plan.md)

### 关键交付

> **Codex audit honesty v0.9:** Hard-coded executor resolve + HTTP sketch; no entry-point plugin wheel. Version Index **unchecked**.

- [ ] entry point registry 与显式配置选型；未知、重复或不兼容 executor 在 Attempt 前 fail-closed。
- [ ] 第二 Executor 使用同一 invoke/result/session 契约，并只获得自身 scoped credential 与 workspace view。
- [ ] lock/evidence 记录 executor kind、model、options 与可复盘的插件版本信息。

### 验收标准

- [ ] Success：同一 package/Harness 仅切换 profile 后，通过第二后端完成公开 run 与独立 evaluation。
- [ ] Mixed backend：同一 task 的不同 Agent profile 可分别走 Codex 与第二 Executor，Harness 不出现后端名称分支。
- [ ] Expected failure：未知 executor、缺失 credential 或能力不满足在 Attempt 前或 invocation boundary 明确失败，不静默降级。
- [ ] Regression：Codex L1 journey 与 `v0.1`–`v0.8` acceptance suites 通过。
- [ ] Genericity：Executor contract/conformance/failure/composition tests 不启动特定 Benchmark，也不读取 task identity 决定逻辑。

## v0.10 — Environment Capability 最小真实资源

### 目标

Harness 可通过 Environment Capability 使用一种真实 Attempt-local 资源，业务 action 留在 package，shared Adapter 无 Benchmark 名分支。

### 起始可运行基线

- Public entrypoint: L1 `bora run`，支持至少两种 AgentExecutor。
- Baseline smoke: `v0.9` 两后端 journeys、`v0.8` isolation negatives 与全部早期 regressions。
- Observable result: Agent 与 evaluator 路径已隔离；尚无真实 stateful Environment 生命周期。

### 演进增量

增加一种按资源类型命名的 Environment Adapter、prepare/action/teardown、allowlist 与 action hard ceiling；是否需要 freeze/getter 由 evaluator input strategy 决定。

### 设计

- [Environment Manager](../docs/design/05-runtime-core.md#85-environment-manager)
- [Benchmark 转换](../docs/design/08-conversion-security-testing.md#16-benchmark-转换)
- [Adapter 第二领域绑定](../docs/design/08-conversion-security-testing.md#173-adapter-第二领域绑定)
- [Spec 09](active/09-v0.10-environment-capability-plan.md)

### 关键交付

> **Codex audit honesty v0.10:** Standalone Postgres adapter tests only; not wired to public journey. Version Index **unchecked**.

- [ ] 一种真实资源 Adapter 与可复现 prepare/health/action/teardown。
- [ ] package-local Tool/action mapping；Adapter 只解释资源协议和 locked resource config。
- [ ] 未授权 action 在 mutation 前拒绝，资源状态与 cleanup evidence 可检查。

### 验收标准

- [ ] Success：公开 journey 通过真实资源完成 action、declared output、独立 evaluator 与 teardown。
- [ ] Expected failure：未声明 action 或资源不可用在 mutation/Harness 启动前 fail-closed，cleanup 有界。
- [ ] Genericity：第二领域/第二类 task 只通过 `bora.yaml` binding 与 package-local code 接入，不新增 Benchmark-specific Adapter module。
- [ ] Regression：`v0.1`–`v0.9` acceptance suites 与两后端 paths 通过。
- [ ] Evidence：只有固定 upstream、限定 task、真实 Agent/Environment/evaluator/cleanup journey 经用户验收后，才可声称该范围 `real-benchmark-verified`。

### 后续 TODO

- [ ] `v0.11`：对已验证单 Trial 路径做 deterministic matrix 展开与串行调度。

## v0.11 — Campaign / 实验矩阵

### 目标

操作者可在前台串行运行确定性配置矩阵，获得多个独立 Trial Result 与可重建比较摘要。

### 起始可运行基线

- Public entrypoint: 单 Trial `bora run`，具备 Agent、隔离、Evaluator 与真实 Environment。
- Baseline smoke: `v0.10` real-resource journey + `v0.1`–`v0.9` regressions。
- Observable result: 单 Trial 可复盘；尚无 Campaign 调度或矩阵摘要。

### 演进增量

Application 层增加 deterministic matrix expansion 与前台串行 Trial 调度；Campaign 只调度 Trial，不解释 Attempt 内 Harness workflow，也不引入后台 durable authority。

### 设计

- [Campaign Coordinator](../docs/design/05-runtime-core.md#89-campaign-coordinator)
- [Budget 与限制](../docs/design/07-budget-evaluation-failure.md#13-budget-与限制)
- [Spec 10](active/10-v0.11-campaign-matrix-plan.md)

### 关键交付

> **Codex audit honesty v0.11:** Matrix expand + serial CLI; variants not injected into lock. Version Index **unchecked**.

- [ ] matrix canonical expansion、稳定 Trial identity 与每 Trial 独立 `LockedTaskConfig` / Result。
- [ ] 前台串行调度、单 Trial failure 隔离与比较摘要。
- [ ] retry 创建新 Attempt，不静默改变 Trial 分母或 variant。

### 验收标准

- [ ] Success：至少两个 variant 生成两个独立 Trial，摘要可回溯各自 lock digest、Attempt、score 与 evidence。
- [ ] Expected failure：非法 matrix key、重复 variant id 或不支持 override 在任何 Trial 启动前 fail-closed。
- [ ] Partial failure：一个 Trial 基础设施失败不会伪装成低分或覆盖其他 Trial Result。
- [ ] Regression：单 Trial `bora run` 与 `v0.1`–`v0.10` acceptance suites 通过。

### 后续 TODO

- [ ] `v0.12`：只有出现明确后台 status/cancel/reopen 需求后，才引入有限 durable authority。

## v0.12 — 后台控制与耐久 authority

### 目标

在已有明确使用需求与独立 Research 结论时，提供跨进程 status/cancel 与被 Active Spec 收窄的最小耐久 authority。

### 起始可运行基线

- Public entrypoint: 前台单 Run 与串行 Campaign。
- Baseline smoke: `v0.11` matrix journey + `v0.1`–`v0.10` regressions。
- Observable result: 前台执行、失败与 cleanup 可复盘；进程退出后不承诺 reopen 或恢复。

### 演进增量

本版本保持条件性：Research 必须先证明后台控制或 durable/reopen 的真实用户需求、authority scope、并发模型与恢复窗口；未完成该闭包时不创建 implementation-ready Spec。

### 设计

- [Core 默认排除 durable/reopen](../docs/design/01-bora-core.md#29-core-明确不包含什么)
- [进程内限制的适用范围](../docs/design/07-budget-evaluation-failure.md#132-进程内限制的适用范围)
- [Spec 11](active/11-v0.12-durable-authority-plan.md)

### 关键交付

> **Codex audit honesty v0.12:** ControlStore sketch only; B3 Research still blocks; conditional. Version Index **unchecked**.

- [ ] 后台 start/status/cancel 最小控制面及明确 owner。
- [ ] durable identity/state 的原子边界、并发与 crash-window 语义由 Research 和 Active Spec 固定。
- [ ] 恢复若不在本版范围，必须明确 fail-closed 与不可恢复状态；不得从数据库存在推导 recovery。

### 验收标准

- [ ] Success：另一个控制进程可查询并取消后台 Run，目标 Run 进入统一 cleanup，状态可复盘。
- [ ] Expected failure：未知/越权/终态 Run 的控制请求失败且不改变状态。
- [ ] Durability：仅对 Active Spec 声明的进程重启与 crash window 做真实演示；未演示范围明确不支持。
- [ ] Regression：前台 run、Campaign 与 `v0.1`–`v0.11` acceptance suites 通过。

### 后续 TODO

- [ ] 新 Research：远程 worker、跨主机调度、完整恢复或全局 dashboard；未立项前保持非目标。


