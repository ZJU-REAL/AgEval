# 08 — Benchmark 转换、测试与安全边界

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含；不依赖 vault 总文档） |
| 摘要 | 转换路径、Bridge、反模式、通用性证明、信任边界。 |

---

## 16. Benchmark 转换

### 16.1. 转换目标

泛化转换是 BORA v2 的产品目标。目标是在不重写 upstream workflow 和 evaluator truth 的前提下，把大部分 Agent Benchmark / Harness 接到同一外层生命周期，并生成可锁定、可运行、可评测、可清理的 Task Package。

转换器应优先自动发现 task loader、Harness/CLI 入口、Agent client 注入点、Environment lifecycle、输出与 evaluator；无法可靠推导的业务参数由转换者确认。自动化程度取决于 upstream 暴露的稳定边界，不以“是否能翻译成统一 Graph IR”衡量。

### 16.2. Upstream owner 盘点

| Upstream 组成 | 需要确认的内容 | 默认处理 |
| --- | --- | --- |
| Task loader | task、input、seed 如何选择 | 映射到 `bora.yaml` 或 Harness 输入 |
| Agent loop | messages、memory、speaker、stop condition | 直接复用 |
| Agent invocation | prompt、Tool、session 接口 | 注入 BORA Agent callback |
| Tool/action | 本地函数、workspace 操作或外部 mutation | 保留业务函数，只桥接外部边界 |
| Environment | prepare、action、teardown，以及是否需要终态 | 映射到资源类型 Adapter；freeze/getter 按 evaluator 需要启用 |
| Artifact | 哪些文件跨 sandbox 或进入 evaluator | 声明 path + publish；materialize 由 Runtime 处理 |
| Evaluator | truth、hidden material、score schema | 原样隔离执行并绑定结果 |
| Upstream tests | 哪些断言证明任务语义 | 保留为 conversion regression |

### 16.3. 五种归属

每个组成只归入一种：

1. 原样复用：upstream memory、router、team object、prompt、local Tool、evaluator。
2. Task-local conversion：参数绑定、callback 注入、路径转换和 result mapping。
3. Harness Core helper：Agent、Context、Tool、Hook、Guard 和 workflow helper。
4. Runtime capability：Agent Provider、workspace、Environment、Artifact、Evaluator 和宿主限制。
5. Infrastructure Adapter：Docker、Codex、数据库、Browser、VM 等执行机制或资源协议。

### 16.4. Bridge 模式

#### Callback bridge

upstream 支持 callback 时，把 `ctx.agent.invoke`、Environment client 或 Artifact helper 包装成它期望的函数签名。内部 memory 和 loop 保持原样。

#### Client wrapper

upstream 依赖 client interface 时，实现窄 wrapper，把 `generate()`、`step()` 或 `query()` 转发到 BORA capability。Wrapper 只转换数据形状。

#### Process bridge

upstream 只能通过 CLI 或独立 server 运行时，在 Attempt runtime 内启动它，通过 JSONL、stdio 或 scoped socket 交换数据。Provider 负责 placement、network、secret、health 和 teardown。

Process bridge 是半自动转换的扩展路径，不改变 MVP 默认的进程内 Harness 假设。

### 16.5. 自动与半自动转换检查表

满足下列条件越多，越适合自动转换：

- task 可以由稳定 ID/seed 选择，输入能序列化或通过已声明路径 materialize；
- Harness 有 Python callable、client interface 或 CLI 入口；
- Agent 调用可以注入 callback/client，或由受控 process bridge 截获；
- 外部 mutation 可以收敛到有限 action schema，并在 Adapter 开始前做 allowlist；
- Environment 有可重复的 prepare/teardown，或能声明为外部受管资源；
- 输出路径和 evaluator 输入可以静态声明；
- evaluator 可离线调用，hidden material 能从 Harness/Agent mount 中剥离；
- upstream 有正向任务和至少一个 negative control 可复用。

出现以下情况时采用半自动转换，由人确认 owner map 和边界：动态发现未声明外部 endpoint、Harness 直接持有 credential、评测依赖在线人工状态、CLI 没有稳定输出协议、task loader 与全局可变状态强耦合。半自动表示生成 package 骨架、候选配置和待确认项，不能静默猜测权限或评分语义。

### 16.6. 转换反模式

- 按 Benchmark 名称在 shared Adapter 中分支；
- 为保留 upstream loop 而复制第二份 Actor/Graph/Memory DTO；
- 把 evaluator 逻辑移进 Harness，或让 Harness 读取 gold 后自报 PASS；
- 把配置无法表达的实验参数藏进环境变量或代码默认值；
- 为单个 task 新增一级 package 目录、Runtime Service 或通用 authority；
- 只跑 fixture/unit test 就宣称 conversion 已完成。

### 16.7. Shared module 的准入

一个 conversion helper 进入 shared package 前，需要同时满足：

- 输入和输出只使用稳定领域概念；
- 不读取 Benchmark、task、角色或业务 action 决定分支；
- lifecycle 和 failure 可以独立说明；
- contract test 不需要启动特定 Benchmark；
- Task Package 可以覆盖或绕过 helper。

未满足条件的逻辑留在 Task Package。这不影响 BORA 统一执行不同 Benchmark。

## 17. 测试与通用性证明

MVP 只设三道完成门；单元测试、Config validation 和 helper conformance 作为门内证据，不扩成 package 作者必须理解的公共测试矩阵。

### 17.1. 真实 journey 与 evaluator negative control

固定一个 upstream task，完成真实 Harness、Agent/Environment、declared output、独立 evaluator 和结果绑定；再提供一个错误输出或错误终态，证明 evaluator 能拒绝或给出低分。两次结果都绑定相同 package/task 来源与 locked config digest。

### 17.2. Fail-closed 与 cleanup

至少触发一次未声明 action、硬顶耗尽、writer 未停或缺失 output，证明副作用在 Adapter 开始前被拒绝或 Evaluator 不启动；随后证明 Provider/Environment 进入统一 cleanup 路径，cleanup failure 只产生 warning，不覆盖已有 score。

这道门同时检查 Harness/Agent 不能读取 `evaluation/`、session 不能跨 Attempt 复用，以及 invalid config 在 Attempt 创建前失败。

### 17.3. Adapter 第二领域绑定

任何声称通用的 Adapter 必须通过声明接入第二个领域或第二类 task，Adapter 代码不新增 Benchmark/task identity 分支。测试使用资源语义和调用参数构造；只能服务单一 Benchmark 的逻辑留在 Task Package。

## 18. 安全与信任边界

### 18.1. Task Package

Task Package 和 Harness 在运行前由用户或 conversion process 接受，并在受控 runtime 中执行。它可以实现 task policy，但不能取得：

- BORA host control；
- Docker socket；
- Provider credential；
- 未声明 network；
- evaluator-only hidden material；
- 其他 Attempt 的 capability。

### 18.2. Agent output

Agent output 按不可信输入处理：

- structured output 经过 schema 校验；
- Tool arguments 先经过 Harness guard；
- 文件路径经过 Workspace boundary；
- 外部 action 经过 Environment capability；
- Agent 自报完成不影响 evaluator verdict。

### 18.3. Capability scope

每个 capability：

- 绑定一个 Attempt；
- 只包含 LockedTaskConfig 授予的范围；
- 使用明确的 actor/workspace/resource scope；
- 在 Harness terminal 后关闭；
- 不能被序列化后跨 Attempt 复用。
