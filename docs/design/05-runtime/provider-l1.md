# Runtime — Provider 与 L1 隔离

| 字段 | 值 |
| --- | --- |
| 父索引 | [05-runtime/README.md](README.md) |

---

## Provider 职责

Provider 负责代码运行位置和 OS 级限制：

- container、VM 或 local process；
- image、platform、working directory；
- UID/GID 和 mount；
- actor-specific 或 invocation-specific WorkspaceView；
- network 和 secret projection；
- process start、timeout、cancel 和 kill；
- 停止 writers；timeout/kill 后确认不再写入即可，不要求独立的干净退出证明。

所有 Agent 使用同一个 Attempt volume 只有在配置明确授予相同 WorkspaceView 时才成立。不同 Agent 需要不同可见性时，Provider 使用独立 mount、PathGrant 或 OS permission。Actor 名称本身不会产生隔离。

## Docker L1 镜像来源（package 拥有 Dockerfile）

1. `provider.kind: docker` 时，package 必须提供 **`environment/Dockerfile`**（或 `provider.dockerfile` 指向的 package 内路径）。
2. Runtime prepare：**确保官方基座** `bora-attempt:l1`（仓库 `docker/attempt`）→ **`docker build -f <package Dockerfile>`** 得到 Attempt 用 image → digest 写入 evidence。
3. 官方基座构建一次、多处 `FROM` 复用；上游基座由 package Dockerfile 自行 `FROM` 并安装**同一 pin 表**声明的入口（禁止 package 自选 floating 版本）。
4. **基座预装（设计契约）：** 最低 coding-agent 验收 entry 的 **engine + ACP 入口** bake-in：
   - Mode 1：`codex`+`codex-acp`、`claude`+`claude-agent-acp`、**`pi`+`pi-acp`**；
   - Mode 2：`opencode` 含 `acp` 子命令；
   - Mode 3：exact Grok pin 的 `grok agent stdio`。
5. Agent **ACP entry 在容器内**执行（不依赖挂载宿主 Homebrew binary）；缺 engine/adapter 则 fail closed，**禁止**以 parent 冒充 L1 PASS，**禁止** invoke 时 `npm i` / `npx latest`。
6. **Parent 侧**运行 BORA ACP client（typed JSON-RPC）；Attempt 镜像**不**安装 Python ACP SDK。L1 通过 `docker exec` 附着容器内 entry 的 stdio。

### 术语：`entry` vs 包名

| 配置 / 文档用语 | 含义 |
| --- | --- |
| `options.entry: pi` | registry **entry_id**（逻辑入口名） |
| `pi-acp`（npm） | Mode 1 官方 ACP 桥包；与 engine `pi` 双装 |
| 禁止 | 将 entry_id 与 npm 包名混用为配置字段 |

## L1 多 Actor 隔离与 SDK 调度面

L1 多 Actor 的最终调用面与 L0 一致：Harness 通过 `Agent.session(profile_id, actor_id=..., max_turns=...)` 获得 opaque session，再执行 `invoke` / `close`。**所有业务向 Agent invoke 必须出现在 package harness（或包内明确编排入口）**；Runtime / Provider 不得再为 package 隐式 one-shot `parameters.question` / `workspace_output`。

`provider.agent_isolation.mode` 支持 `shared-container` 与 `container-per-group`。`actor_id` 是隔离 principal，profile 只选择 executor、model 与 credential binding；Config lock 仅保存 actor、group、profile allowlist 与 `shared_write` 等逻辑拓扑。Provider 在 Attempt prepare 时建立 `actor_id → ExecutionTarget`，ParentAgentService 再建立 opaque `session_id → actor_id + profile_id + target_id + generation` 绑定。Docker container id、UID/GID、socket path 与 live handle 只进入 Runtime 私有 cleanup ledger；Harness、SDK、lock 与公开 evidence 均不得获得 raw handle，evidence 至多记录 opaque `target_id`、image digest 与实际 isolation mode。

`shared-container` 为各 actor 分配不同 numeric UID 与私有 HOME；同 group 只有显式 `shared_write` 可经 shared GID 写入。`container-per-group` 为每个 group 建立独立 container，单 actor group 即 per-agent container，v1 不提供跨 container 共享可写 volume。SDK 经 worker-local scoped channel 把 open/invoke/close 交给 ParentAgentService；父侧校验 actor/profile 绑定、执行前 hard ceiling 与 credential projection，再要求 Provider 在已绑定 target 中以对应 UID/GID 执行。target 创建失败、unknown actor、profile 越权、credential 缺失、relay 中断、generation 不匹配或容器内 executor 不可用均 fail closed，**禁止**改走 host CLI。

Loop 中间文本和结构化上下文由 Harness memory 保存并拼入下一轮 prompt，Core 不感知。`shared_write` 只覆盖同容器显式文件协作；跨容器物理 handoff 不在本设计默认范围内（见 Issues 若单独立项），终局产物继续使用 `publish_*`。绑定约束见本节与 [AGENTS.md](../../../AGENTS.md)「L1 多 Agent 调度」。

## Network（设计契约）

`provider.network` 声明 Attempt 级网络策略（如 `bridge` | `none`）。所有 Agent target 共用该 Attempt 级策略。细粒度 per-actor 网络隔离若未进入稳定契约，则标为**非目标**或另开 Issue 跟踪——design 正文不写「排期未实现」状态句。
