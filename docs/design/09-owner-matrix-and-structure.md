# 09 — Owner 矩阵、决策检查表与最终结构

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含；不依赖 vault 总文档） |
| 摘要 | 职责归属、决策检查、目标仓库结构。 |

---

## Owner 矩阵

| 行为 | `bora.yaml` | Config Core | `harness.py` / upstream | Harness Core | Runtime Core |
| --- | --- | --- | --- | --- | --- |
| Harness entrypoint | 声明 | 校验并锁定 | 实现 | 无 | 启动 |
| 实验超参数 | 声明唯一值 | 合并、校验、锁定 | 通过 `ctx.params` 解释并使用 | typed view/helper | 记录 Trial identity |
| Agent loop、Actor、Router | 参数可提供 profile 引用和上限 | 不解释算法 | 拥有 | 可选 Agent helper | 执行真实 invocation（经 Agent Service） |
| Agent 后端（ACP entry：Codex / Claude Code / Pi…） | `agent_profiles` + `parameters.models` 引用 | 校验 profile→executor/entry 并锁定 | 只传 profile id | `ctx.agent.invoke` | **Agent Service** + **Executor**（`acp` + entry / `openai-http` / 插件） |
| 用户自研 Core 插件（含非 Agent 面） | 声明对应 kind / 配置选型 | kind 必须已注册；lock 写 `extension_bindings` | 不直接依赖插件 SDK | 经 Capability / 配置消费 | 扩展注册表 resolve、凭据投影、digest 锁定；`bora plugin install` 不改 profiles |
| 同 task 多后端 / 换后端实验 | 多 profile 或 variant 改引用 | 同上 | 不改 workflow 代码 | 同上 | 同上 |
| messages、Context | 参数可声明 strategy | 原样锁定参数 | 拥有状态 | transform、compaction | 不保存 team memory |
| 本地 Tool | 参数声明上限 | 锁定参数 | 定义 callable 和 policy | ToolSet、hooks、guards | 无 |
| 外部 Tool action | 声明 Environment 和硬上限 | 校验 capability | 决定何时调用 | client helper | Environment/Network/Secret |
| branch、fan-out、join | 参数声明并发或最大次数 | 锁定参数 | 拥有算法 | workflow helper | Provider capacity ceiling |
| 普通 typed handoff | 无 | 无 | Python object/message | 可选 typed helper | 无 |
| 跨 sandbox 文件 | 声明 WorkspaceView 和 output path | 校验引用 | publish declared output | publish helper | 路径检查、digest、materialize |
| wall time、memory、process | 声明 | 校验范围 | 可提前停止 | RunScope | 最终强制 |
| evaluator verdict | 声明入口和输入 | 校验引用 | 不发布 verdict | 无 | clean runtime 和结果绑定 |

## 决策检查表

新增能力前按顺序检查：

1. 这个值是否需要配置、比较或覆盖？需要则写入 `bora.yaml`，由 Config Core 读取。
2. 这个行为能否由一个 Harness 在当前进程中用普通 Python 完成？可以则留在 `harness.py`。
3. 多个 Harness 是否反复编写同一种样板？是则提炼为可选 Harness Core。
4. 这个动作是否跨进程、信任域、外部资源或宿主权限？是则进入 Runtime capability。
5. 是否已经出现并发竞争、崩溃恢复、后台 reopen 或跨进程共享状态？出现后再增加 durable store 或独立 lifecycle component。
6. Shared 实现是否需要读取 Benchmark、task、角色或业务 action 才能工作？需要则返回 Task Package。
7. 能否用普通 callable 或已有 Capability 完成？可以则不新增 Adapter；内部是否使用 Port 由实现决定。
8. 真实 journey + negative evaluator、fail-closed + cleanup、Adapter 第二领域三道门是否有证据？缺少哪一道，就不能宣称转换或通用能力完成。

## 最终结构

```text
bora.yaml
  = Task 的唯一规范配置入口

Config Core
  = load_and_lock：读取、合并、校验、canonicalize、digest 和锁定配置

harness.py / upstream Framework
  = Agent loop、Context、Tool、Router 和动态工作流

Harness Core
  = Agent、Context、Tool、Hook、Guard 和 Workflow helper

Runtime Core
  = Attempt、Provider、Environment、Workspace、declared output、硬顶和 Evaluator authority

Adapter / 插件
  = 按 Core 契约实现资源、协议或执行机制（可 first-party 或外置分发）
```

端到端链路是：

```text
bora.yaml
  → Config Core.load_and_lock()
  → LockedTaskConfig
  → Runtime 准备 Provider、Workspace 和 Environment
  → Runtime 注入 HarnessContext
  → harness.py 动态编排
  → Agent / Environment / Workspace / Artifact Capability
  → HarnessTerminal
  → stop writers 与 materialize evaluation inputs
  → 独立 Evaluator
  → flat Result + cleanup warning
```

## 相关资料

历史讨论与外部参考（保留标题，便于追溯；**不构成**本仓设计权威）：

- BORA 动态 Harness 与精简 Core 决策（vault 历史笔记）
- BORA Code-first Harness 转向评估（vault 历史笔记）
- 流行 Benchmark 与 Harness 抽象研究（vault 历史笔记）
- Graph Engineering SDK 与 BORA 插件边界调研（vault 历史笔记）
- [A harness for every task：Dynamic workflows in Claude Code](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code)
- [Claude Code workflows](https://code.claude.com/docs/en/workflows)
- [earendil-works/pi](https://github.com/earendil-works/pi)
