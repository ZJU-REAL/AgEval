# 00 — 产品目标、背景与边界

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含） |
| 摘要 | 产品定位、成功标准、红线、可见性投影、问题背景与设计修正。 |
| vault 章节 | §0–§1（及总文导语） |

---

> [!important] 设计决定
> **Bounded Orchestration for Runtime Agents（BORA）** v2 的产品目标是在简洁 Core 上，使大部分上游 Agent Benchmark / Harness 能以可重复方式转换为 BORA Task Package，并完成自动测评与结果绑定。Core 保留配置锁定、Attempt 生命周期、Provider 物理隔离、**可见性投影**、Capability 和独立 Evaluator；`harness.py` 或 upstream Framework 拥有 workflow。设计口令是：**边界硬、契约薄、实现可胖**；精简只针对过度设计，不砍可见性等核心机制。
>
> **扩展原则：** Core 在稳定契约上允许用户/第三方实现**定制化插件**并分发（entry point + 包安装，如 `pip`）。**不限于 Agent 后端**——Pi 的 `invoke` 只是示例；Provider、Environment、Artifact 等采用同一「接口 + 注册 + 配置选型」模式。调度面（如 Agent Service）留在主仓；可插拔的是各 Adapter 实现，不是开放应用商店。

本文围绕两个问题展开：不同上游 Harness 如何沿同一转换路径接入 BORA，以及 Core 用多薄的公共契约守住可复盘、物理隔离和 evaluator truth。文中的 `database-52-mvp/` 与 `database-52/` 是概念 package 名称：前者展示最短可用路径，后者展开完整 envelope；相关配置、Harness 和 Runtime 对照已完整写入 [02-task-package-and-config.md](02-task-package-and-config.md) 与 [10-examples-database-52.md](10-examples-database-52.md)，不依赖仓库外目录。单个示例只证明一种模式，不定义 BORA 的能力边界。

后续 Spec 与实现**只以本目录 `docs/design/` 为准**。与历史 vault 长文的章节对照与变更规则见 [../README.md](../README.md) 中「与 vault 总设计的对齐」。

## 0. 产品目标与 MVP 边界

### 0.1. 成功标准

BORA v2 的成功标准是：面对结构不同的 Agent Benchmark，转换者可以复用同一套 owner map、Capability 和 evaluator barrier，优先保留 upstream workflow，只补齐配置、物理边界、外部效果与结果绑定。Roadmap 中的 task 是回归样例，不能成为 shared Adapter 按 Benchmark 名称分支的理由。

成功度量是可转换 Harness 的覆盖面与单个转换的人工/代码成本，不是 Roadmap 示例数量；`database-52*` 只承担回归样例职责。

转换能力同时满足四项要求：

1. **精简：** 只去掉讨论过的过度设计与过度防御仪式（例如 Config 多阶段公开 DTO、Artifact 用户类型阶梯、未证明必要的九步/四提交叙事）。**不**精简核心且实现成本合理的机制——包括**可见性控制（projection / view / mount / materialize）**与**Attempt evidence / Agent 轨迹落盘**。package 作者仍主要面对一份 `bora.yaml`、一个 Harness 入口、一个 Evaluator 入口和少量 Capability。
2. **可拓展：** 隔离、Environment 终态和 transport 按档位或策略增加，不要求每个 task 预先配置能力全集。
3. **泛化转换：** §16 规定自动、半自动与手工 bridge 的判断方式；shared 实现以第二领域绑定证明通用性。
4. **可观察与可训练：** 一次 Attempt 结束后，操作者与训练管线必须能从固定 evidence 目录读取 Agent 执行轨迹（请求/事件流/归一化输出/usage 等），用于人工复盘、失败分析与轨迹训练数据导出。扁平 `Result` 不够；**轨迹落盘是 Core 义务**，不是 Harness 可选副作用。

### 0.2. 红线

| 能力 | 最小保证 |
| --- | --- |
| 单一 `bora.yaml` 与 Trial 锁定 | 参数、外部 envelope 和 evaluator contract 可比较、可复盘 |
| Code-first Harness | workflow、Actor、Router、Tool 组合、branch 和 handoff 由 `harness.py` 或 upstream Framework 掌握 |
| Attempt 与 Provider | Runtime 掌握执行身份、物理隔离、writer stop 和 cleanup |
| Capability | Harness 只经 agent、environment、workspace、artifacts 等窄操作面触达外部能力 |
| **可见性控制** | 不同消费者（Harness / Agent / Evaluator / Adapter）只获得声明范围内的路径、secret、网络与参数视图；见 §0.4 |
| 独立 Evaluator | `HarnessTerminal.completed` 不等于 PASS，评分只能由独立 evaluator 形成 |
| 硬顶与 allowlist | Runtime 强制 wall time、memory、Agent invocation、Environment action，并在执行前拒绝未声明 action |
| hidden material | gold、hidden test 和 evaluator-only material 不挂载给 Agent，也不挂载给 Harness |
| **Agent 轨迹落盘** | 每次经 Agent Service 的真实 invocation 必须在 Attempt evidence 树中落盘（默认 per-invocation JSONL 事件流 + 归一化摘要）；`Result.logs` 指向该树；轨迹不得含 host credential；轨迹**不得**代替 evaluator verdict |

### 0.3. MVP 假设与非目标

MVP 默认单 Attempt、前台串行、进程内 Harness。Environment 的最小生命周期是 prepare / action / teardown；artifact-only 评测不强制 freeze。Provider 通过 `assurance` 选择 L0/L1/L2 隔离档，本轮主示意使用 L1 path views。

**精简范围**仅针对过度设计。下列内容可以保留为内部实现或未来扩展，但不进入「package 作者必学」的公共仪式：

- Loaded / Resolved / 多套可持久化 *Config* projection **DTO 阶梯**（不是「可见性 projection」能力本身）；
- ArtifactRef / MaterializedArtifact / SealedArtifact **用户类型**阶梯（内部 materialize/digest 仍可存在）；
- 九步评测仪式和四个公开 commit point；
- 不把 Port 提升为 package 作者必学层，也不强制 Capability → Port → Adapter → Service 四层主叙事；对外只讲 Capability + Adapter；
- 每次 Agent invocation 重复核验已经绑定的 Attempt/profile/workspace；
- 对外完整**阶段结果树**作为聚合器必选 schema（内部/操作者 evidence 树**必须**存在，见 §0.2 轨迹落盘）；
- 所有 task **强制** freeze、per-actor UID/GID、durable/reopen；
- 默认把 **Capability transport** 做成 JSONL/stdio 跨进程（与 evidence 目录里的 JSONL **不是同一件事**；轨迹落盘默认 JSONL 文件）；
- 通用 Handoff、BranchAuthority、Graph IR 和 workflow receipt 系统。

### 0.4. 可见性投影（保留的一等机制）

**控制可见性是一等能力，不是被精简掉的对象。** `projection` / `view` 在本文中的正当含义是：给某个消费者一份**声明范围内的受限视图**。实现上按边界拆分 owner，而不是用 Config 字段 ACL 假装隔离。

| 视图 / 投影 | Owner | 作用 |
| --- | --- | --- |
| Workspace path view | Provider + `provider.workspace.views` | Harness / 各 Agent 能读哪些路径、写哪些路径 |
| Secret / credential projection | Runtime credential store | 只有获准的 Adapter/进程拿到 token，不进 Agent prompt 默认可见面 |
| Network projection | Provider network policy | 进程能连哪些 endpoint |
| Artifact materialize 视图 | Artifact capability | 跨 sandbox 或进 evaluator 时的只读副本与 consumer scope |
| Parameter view（`ctx.params`） | Config lock + HarnessContext | Harness 只读 `parameters`，不必也不应解析整份 YAML / gold |
| 文本 / prompt 可见性 | Harness Context 或 upstream memory | 模型消息过滤；**不能**替代物理 mount 隔离 |

**硬规则：** gold 与 evaluator-only material 的隔离必须靠 **不 mount + 评测前 materialize**（以及按需的网络/secret 边界），不能只靠「配置投影时删掉字段」。Config 侧可以提供轻量只读 view（如 `ctx.params`），但不发明多消费者 Loaded→Resolved→Projected 公开流水线作为安全边界。

## 1. 项目背景

### 1.1. BORA 要解决的问题

BORA 用同一个公开入口执行不同 Agent Benchmark。一个 Benchmark 通常包含 task loader、Agent loop、Tool、Environment、workspace、evaluator 和结果聚合，但这些部分的组织方式差异很大：

- Terminal 类任务可能只启动一个 Agent，让它在容器里完成文件或终端操作；
- Tool-Agent-User Benchmark 会维护 Agent、用户模拟器和外部业务状态之间的多轮交互；
- 多 Agent Benchmark 可能包含 Planner、多个 specialist、动态 follow-up、Reducer 和 team memory；
- Browser、VM、数据库和桌面 Benchmark 依赖不同的 Environment lifecycle；
- hidden tests、gold labels、外部终态和 trajectory metrics 对 evaluator 隔离有不同要求。

BORA 需要统一的是一次实验如何准备、运行、评测、保存结果和清理资源。Benchmark 内部如何组织 Agent 和数据流，继续由它自己的 Harness 或上游 Framework 决定。失败模式是每接入一个 Benchmark 就给 Runtime 增加一组 task-aware service、Adapter 或 workflow schema；成功模式是大部分转换复用相同外层边界，只在 Task Package 中保留必要的业务 glue。

### 1.2. 从静态配置驱动开始

早期方案接近 Harbor 类静态编译模型：Benchmark 的 Actor、Graph、Tool、Policy、Environment 和 Evaluator 都写进配置，Compiler 再生成统一执行计划。这个设计容易做运行前检查，也能形成确定的 plan，但它要求 BORA 预先理解每一种工作流结构。

真实 Benchmark 接入后，静态模型不断扩张：

- 动态 speaker 需要 Router schema；
- 多 Agent 结果传递需要 Context、Handoff 和 visibility schema；
- output-dependent follow-up 需要 Branch、Join 和 Planner authority；
- Tool 调用检查需要 Tool declaration、dispatcher、budget 和 receipt；
- 上游 memory、team object 和 loop 需要再次映射为 BORA DTO。

Config、Compiler 和 Runtime 逐渐承担了第二套 workflow engine 的职责。接入一个 Benchmark 的工作量开始取决于“能否把 upstream 代码翻译成 BORA 的静态语言”，而不是“能否在 BORA 的外部执行边界中运行 upstream Harness”。

### 1.3. 引入 `harness.py` 后的问题

`harness.py` 让循环、条件、并发和动态数据依赖回到 Python，控制流表达能力得到改善。但旧设计仍把 Actor、Tool、branch、join 和 collaboration 信息写入 `bora.yaml`、locked plan 与 Runtime authority。于是同一语义出现多个 owner：

- `harness.py` 已经实现 Agent loop，YAML 仍重复声明 Actor 和 branch；
- Tool 的业务名称、Actor 绑定和调用次数同时存在于 YAML、SDK 和 Runtime dispatcher；
- 上游 Framework 已经维护 memory，BORA 仍要求生产 `HandoffRef`；
- 一个进程内计数器可以完成的限制，被扩展成宿主 Port、Service 和 receipt 链；
- 每个配置字段都可能要求修改 schema、Compiler、locked DTO、Runtime 和 Adapter。

这类耦合没有随着 `harness.py` 出现而自动消失。必须重新划分 Config、Harness 与 Runtime 的所有权。

### 1.4. 动态工作流与精简 Agent Core 的启发

[Anthropic 的动态工作流](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code)把 loop、branch 和中间结果留在脚本中，运行环境负责 sandbox、权限和资源上限。这个做法说明，统一执行环境可以容纳不同的内部工作流。

[earendil-works/pi](https://github.com/earendil-works/pi)展示了另一条有用边界：Agent loop 可以由 messages、tools、状态和少量 hooks 组成。`transformContext`、`beforeToolCall`、`afterToolCall`、`shouldStopAfterTurn` 都是普通函数或可组合对象。数据库、宿主权限和完整 workflow platform 不需要进入最小 Agent Core。

BORA 面向的对象比单个 Agent loop 更外层。可以把它理解为 Harness 的执行内核：Harness 负责算法，BORA 负责配置、运行位置、外部能力、产物和评测。

### 1.5. 本轮设计修正

动态 Harness 解决了工作流表达问题，但参数管理仍需要一个统一入口。Tool 上限、Agent 轮数、模型 profile、并发、retry、context strategy 等值如果散落在 `harness.py`、环境变量和附加配置中，实验难以比较，也无法确认一次 Trial 实际使用了什么参数。

本轮设计增加一条强约束：

> [!note] 单一配置来源
> 每个 Task Package 只有一个规范 task 配置文件 `bora.yaml`。Config Core 是唯一读取者。所有可调整、可比较、可被 experiment variant 覆盖的值都从这里进入同一份 `LockedTaskConfig`。锁定后做轻量可见性投影：Harness 通过 `ctx.params` 读取 `parameters`，Runtime 从锁定对象读取 envelope 并实施 workspace / secret / network mount。gold 隔离依靠 Provider mount 与 evaluator materialization，**不**依靠 Config 字段 ACL，也**不**取消 projection 能力本身。

参数写入配置，不意味着 Runtime 要解释其业务含义。`max_tool_calls` 可以由 Config Core 读取、由 Harness 的 `CallLimit` 执行；`wall_time_seconds` 同样来自 `bora.yaml`，但由 Provider 强制。配置位置统一，执行 authority 按边界分层。
