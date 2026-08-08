# Runtime — Agent Service 与 ACP inlet

| 字段 | 值 |
| --- | --- |
| 父索引 | [05-runtime/README.md](README.md) |
| 章节锚点 | 原 design §8.4 |

---

## 术语：Task Harness ≠ Agent 后端

| 概念 | 是什么 | 谁拥有 |
| --- | --- | --- |
| **Task Harness** | package 的 `harness.py` / upstream workflow | Task Package |
| **Agent 后端 / Executor** | 真正执行一次模型/agent 调用的实现。**coding-agent** 走 `executor: acp` + `options.entry`；另保留 `openai-http`（api-client） | Runtime **Agent Service** + Executor Adapter |
| **agent_profile** | 命名绑定：`executor` + `model` + `options` + `workspace_view` | `task.yaml` / Database 成员配置 → LockedTaskConfig |
| **ACP entry** | 标准 ACP stdio 入口（官方 shim / 原生 `acp` 子命令 / 厂商包）；翻译 vendor 私有协议 | 进程外二进制；由 registry pin，L1 镜像 bake-in |
| **profile 引用** | Harness 使用的逻辑名（如 `parameters.models.planner`） | `parameters`（可被 Campaign override） |

口语里的「换 agent harness」在 BORA 里指 **换 Agent Executor / profile**，不是换 `harness.py`。Task workflow 保持稳定，后端可替换，这是可比实验的基础。

## 配置如何表达切换与混用

```yaml
agent_profiles:
  # coding-agent：统一 ACP client + entry
  - id: specialist-codex
    executor: acp
    model: o4-mini
    workspace_view: agents
    options:
      entry: codex              # registry entry_id；非 package 自带 command

  - id: specialist-cc
    executor: acp
    model: claude-sonnet-4
    workspace_view: agents
    options:
      entry: claude-code

  - id: planner-opencode
    executor: acp
    model: entry-default        # 或 entry 支持的 exact model id
    workspace_view: agents
    options:
      entry: opencode

  - id: planner-pi
    executor: acp
    model: entry-default
    workspace_view: agents
    options:
      entry: pi                 # Mode 1: engine pi + pi-acp；entry_id=pi，包名 pi-acp

  # api-client（非 coding-agent ACP 路径）
  # 可选 per-profile 上游路由（与 model 同级）：
  # - base_url: non-secret endpoint（进入 lock digest）
  # - api_key: 环境变量 *名* only（locator）；值来自 host/.env，
  #   投影进 Executor 时使用 — 永不写入 lock/evidence
  - id: glm-coding-http
    executor: openai-http
    model: glm-4.7
    base_url: https://open.bigmodel.cn/api/coding/paas/v4
    api_key: zhipu_coding_api_key

parameters:
  models:
    specialist: specialist-codex   # 或 specialist-cc
    planner: planner-opencode      # 同 task 内混用不同 ACP entry
    reducer: specialist-codex
```

- **整 task 换后端（Codex entry → Claude entry）：** 改 profile 的 `options.entry` / `model` 或 `parameters.models.*` 引用；**不必改** `harness.py`。
- **同 task 不同 Agent 用不同后端：** 各 role 引用不同 profile id；specialist=Codex entry、planner=OpenCode entry 合法。
- **同 entry 不同模型：** 改 `model`（经 ACP config option 绑定）或并列 profile。
- **上游 endpoint / 密钥定位：** 可选 `base_url` 与 `api_key`（env 名）与 `model` 同级；`bora run` 从 package/cwd/repo `.env` 注入宿主环境后，Runtime 按 locator 投影给 Executor / ACP child env。

`load_and_lock` 必须校验：每个 `parameters` 中的 profile 引用存在；每个 `executor` kind 在 Agent Service 的注册表中可用；`executor: acp` 必须有 registry 内 `options.entry`；`workspace_view` 存在；若声明 `base_url`/`api_key` 则校验 URL 与 env 名形态（`api_key` 不得为 secret 值）。锁定结果含 profile → executor/entry/model/base_url/api_key(locator) 与 descriptor digest 的解析快照，进入 Trial identity / digest。

**禁止：** 在 parent 内按 vendor 再写第二套 stdout scrape（含 container heuristic JSON）。coding-agent 配置形状为 `executor: acp` + `options.entry`，不是 `executor: codex|claude-code|pi|opencode` 私有 kind。

## Agent Service（Runtime）

Agent Service 是 Runtime 内的调度面，不是插件市场：

```text
ctx.agent.invoke(profile_id, messages, ...)
  → 查 LockedTaskConfig.agent_profiles[profile_id]
  → 选 Executor Adapter(executor kind)
  → 注入 credential / workspace view / network projection
  → 调后端：
       acp         → parent typed ACP client ↔ host/L1 ACP entry stdio
       openai-http → API client
       <custom>    → entry-point 注册的其它 mechanism kind（须 fail closed）
  → 归一化为 AgentResult（content / structured / usage / session）
```

职责：

| 职责 | 说明 |
| --- | --- |
| Profile 解析 | 把逻辑 profile 绑到具体 executor + model + options（含 `options.entry`） |
| Executor 路由 | `acp`（单一 client + entry registry）、`openai-http`、经 entry point 声明的其它 kind；**不是**每个 vendor 一套 stdout parser |
| Session 绑定 | 创建时固定 Attempt + profile + workspace；禁止跨 Attempt 复用 |
| 统一 invoke 契约 | Harness 只见 messages / schema / tools 意图，不见各 CLI/ACP 细节 |
| 额度与安全 | `limits.agent_invocations`、capability close、secret 不进 package 代码 |
| 可观测与落盘 | 每次 invoke **同步**写入 Attempt evidence：identity、profile/executor/entry/model、请求摘要、后端事件流、归一化 content/structured、usage、latency、失败 kind；供复盘与轨迹训练（[evidence.md](evidence.md)） |

Harness / Harness Core 的 `Agent(..., model_profile=params.planner_model)` **只传 profile id**；不得 `import` 某个具体 agent CLI SDK 写死后端。

## ACP 作为 coding-agent 统一 inlet

声明 [Agent Client Protocol](https://agentclientprotocol.com/) wire 的 coding-agent 后端：

1. **一个** BORA ACP client（parent process），出口恒为 `AgentResult` + evidence events。
2. Vendor 差异只在 **entry descriptor**（Mode 1 官方 shim / Mode 2 原生 `acp` / Mode 3 厂商包）与 **镜像/host pin**，不在 BORA 内复制私有 stdout scrape。
3. Host 与 L1 **共享** session/result mapper；L1 只做 placement（`docker exec -u/-w`、UID/GID、env）。缺 entry/engine → fail closed，**禁止**回退私有 CLI scrape 或未投影 host binary。
4. L1 官方基座 **build 期 bake-in** 最低验收 entry 的 engine 与 ACP 入口（Mode 1 双装，含 **Pi：`pi` + `pi-acp`**）；见 [provider-l1.md](provider-l1.md) BOM。
5. `openai-http` 保持独立 `api-client`。Pi 的 coding-agent 路径为 ACP entry（registry `entry_id: pi` / npm `pi-acp`），不是私有 `--mode json` scrape。
6. ACP `end_turn` / 完整轨迹 **≠** PASS；PASS 仍仅独立 evaluator。

**可见性与 permission（两层）：**

| 层 | 含义 | 策略 |
| --- | --- | --- |
| 物理上下文 | 进程看到/写入的路径 | Provider mount + actor UID/GID + `docker exec -w` |
| ACP permission | tool call 协议放行 | batch **默认 auto-approve**；记入 evidence；**不**提权、**不**突破未 mount / 无权限路径 |
| 工具落点 | 谁执行 open/write | ACP entry 子进程（L1 容器内 actor），非 parent 代持 host fs |
| `session/new.cwd` | 逻辑工程根 | 必须等于已投影 workspace 绝对路径 |

`session/request_permission` 的 approve 只是「允许 agent 继续该 tool」；Linux DAC 与容器 mount 仍是硬边界（non-root 无法写 root 私有目录）。Elicitation 默认 decline。

**非目标：** parent 内 vendor 私有协议第二套 parser；invoke 时网络装包；把 ACP permission 当作 filesystem 提权。

## 归一化 invoke 契约（跨后端）

所有 Executor Adapter 至少支持：

```python
result = await ctx.agent.invoke(
    profile_id="planner-pi",
    messages=[{"role": "user", "content": "..."}],
    output_schema=optional_json_schema,  # 后端不支持则 Adapter 降级/报错策略进 lock 说明
    tools=optional_tool_specs,           # 仅当该 executor 支持 tool loop
    session=optional_handle,
)
# result: content, structured_output?, usage, session_handle?
```

后端能力差（有的无 structured output、有的 tool 形态不同）由 **Adapter 适配 + profile/options 声明**，不由 Task Harness 分支 `if executor == "acp" and entry == "codex"`。若某后端无法满足 task 所需契约，Config validation 在 Attempt 前失败，而不是运行中静默降级出不可比分数。

## 热路径与限制

创建 session 时，Runtime 检查 Attempt identity、profile（含 executor/model/entry）、WorkspaceView 和 capability scope，并将绑定结果固定。`ctx.agent.invoke` 热路径只检查 capability open、deadline/cancel、`limits.agent_invocations` 与 Executor 调用结果。

Session handle 绑定当前 Attempt 和 **profile id**（从而绑定 executor/entry），不能跨 Attempt 复用，也不能在同一 session 上中途更换 executor。

## 扩展模型：Core 开放接口 + 可分发插件

BORA **允许用户与第三方按 Core 契约实现定制化插件**，并以 Python 包装分发（例如 `pip install bora-executor-my-api`）。这不是开放技能商店，也**不是**只能扩展 Agent：

| 做 | 不做 |
| --- | --- |
| Core 固定薄接口（如 `AgentExecutor`；其它扩展面各自有契约） | 插件任意 patch Core 源码 |
| 插件包实现接口并用 **entry point 注册 kind** | 未在配置中引用的插件静默改行为 |
| `task.yaml` / Database 配置选型启用 | 运行中热装、浮动 `latest` |
| 凭据由 Runtime **投影**进插件运行环境 | 密钥写入 package / 配置文件 |
| 插件 version/digest 进入 lock（可复盘） | 评测路径默认信任任意远程市场 |

**调度面留在主仓**（Agent Service 负责路由、session、额度、投影、归一化）。**可插拔、可外置分发的是各扩展面的实现包**。

> [!important] 扩展面不限于 Agent invoke
> Core 在多处开放稳定契约。下表是优先鼓励外置实现的扩展面；下文以 **自定义非 ACP Agent kind** 示范全链路，同一「接口 → 注册 → 配置引用 → 凭据投影」模式适用于其它行。

| 扩展面 | Core 开放的契约（方向） | 配置选型（例） | 示例实现 |
| --- | --- | --- | --- |
| **Agent 后端** | `AgentExecutor.invoke` | `agent_profiles.executor`（+ `options.entry` for `acp`） | 内置 `acp`、`openai-http`；第三方自定义 kind |
| **Provider** | 隔离与 workspace 执行协议 | `provider.kind` | `docker` / `local` |
| **Environment** | prepare / action / teardown（+ 可选 freeze） | component / resource kind | `postgres` / `browser` |
| **Artifact** | publish / materialize 策略 | `artifacts` 与 materializer 实现 | filesystem 等 |
| （可选）Event sink | 观测出口 | Run 级声明 | 日志 / 导出 |

装包如何生效（不是给 Core 打二进制补丁）：

```text
pip install bora-executor-my-api
  → 包元数据登记 entry point（如 bora.agent_executors / my-api）
  → 调度面启动或 load_and_lock 时扫描 entry points
  → registry["my-api"] = MyApiExecutor
  → 仅当 agent_profiles[].executor == "my-api" 时被调用
```

### 示例接口：AgentExecutor

```python
# bora.agent_service.contract
from typing import Any, Protocol


class AgentExecutor(Protocol):
    """Agent 后端插件必须实现的薄接口（其它扩展面有各自 Protocol）。"""

    kind: str  # 与 entry point 名、配置 executor 字段一致

    async def invoke(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any],
        credentials: dict[str, str],
        session: Any | None,
    ) -> dict[str, Any]:
        """
        返回归一化 dict，至少建议包含：
          content: str
          structured_output: object | None
          usage: mapping
          session_handle: object | None
        """
        ...
```

Harness 仍只调用 Capability：

```python
result = await ctx.agent.invoke(
    profile_id="planner-http",
    messages=[{"role": "user", "content": "..."}],
    output_schema=None,
    session=None,
)
```

Agent Service：解析 profile → `registry[profile.executor]` → 注入 `credentials` 与投影环境 → 插件 `invoke` → `AgentResult`。

发现与注册（Agent 面示意）：

```python
# bora.agent_service.registry
from importlib.metadata import entry_points


def load_executor_registry() -> dict[str, type]:
    registry: dict[str, type] = {}
    for ep in entry_points(group="bora.agent_executors"):
        cls = ep.load()
        registry[ep.name] = cls  # e.g. "my-api" -> MyApiExecutor
    return registry
```

插件包元数据（示意）：

```toml
# bora-executor-my-api/pyproject.toml
[project]
name = "bora-executor-my-api"
version = "0.1.0"
dependencies = ["bora-core>=0.1"]

[project.entry-points."bora.agent_executors"]
my-api = "bora_executor_my_api.executor:MyApiExecutor"
```

`load_and_lock`：若 profile 的 `executor` 不在 registry → Attempt 前失败。锁定记录含 kind 与插件版本/digest。

### 示例：自定义 API Executor 插件（非 coding-agent 私有 CLI）

**仅演示 Agent 扩展面。** coding-agent 请用内置 `executor: acp` + `options.entry`。Provider / Environment 等面写法类似，只是接口与 entry point 组不同。

用户本机/CI 在 `.env` 放测试 key；Runtime 只把密钥投影给 Executor，不进 `harness.py`，也不进 Agent 可读 workspace。

**配置（package）：**

```yaml
agent_profiles:
  - id: planner-http
    executor: my-api
    model: default
    workspace_view: agents
    options: {}

parameters:
  models:
    planner: planner-http
```

**凭据（宿主，不进 git）：**

```bash
# .env 或 CI secret
MY_API_KEY=sk-...
```

Runtime 投影后，Executor 收到 `credentials={"MY_API_KEY": "..."}`（或仅注入 Executor 进程环境）。

**插件实现（用户/第三方包）：**

```python
# bora_executor_my_api/executor.py
from __future__ import annotations

from typing import Any


class MyApiExecutor:
    kind = "my-api"

    async def invoke(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any],
        credentials: dict[str, str],
        session: Any | None,
    ) -> dict[str, Any]:
        api_key = credentials.get("MY_API_KEY")
        if not api_key:
            raise RuntimeError("MY_API_KEY missing from credential projection")

        # client = MyApiClient(api_key=api_key, **options.get("client", {}))
        # raw = await client.complete(model=model, messages=messages)
        raw_text = "..."  # from raw
        return {
            "content": raw_text,
            "structured_output": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "session_handle": session,
        }
```

同 task 其它角色仍可用 `executor: acp` + 不同 entry（不同 profile）。Task Harness 无需 `if backend == "my-api"`。

**内置对照：** first-party 提供 `acp`（entry registry）与 `openai-http`；任意其它 mechanism 实现同一接口并登记 entry point，即可被 `executor: <kind>` 引用。**禁止**为每个 coding-agent vendor 在 Core 内再写一套私有 stdout scrape。

### 定制插件作者检查表（各扩展面通用）

1. 是否只依赖 **稳定领域概念**，不读取 `task_id` / Benchmark 名做分支？  
2. 是否在约定 entry point **组**下注册了 **唯一 kind**？  
3. 密钥是否仅来自 **Runtime 投影**，而非扫描用户全盘或写死在包内？  
4. 失败是否可在 Attempt 前或调用时给出明确错误，而不是静默降级出不可比分数？  
5. Task Package 是否仍可在改配置选型后不改业务 workflow 代码？  
6. 版本是否可 pin，并进入 Trial 记录？

满足以上即可作为 **用户自研定制插件** 分发；平台可附带 first-party 参考实现（如 `acp` / `openai-http`），但不阻止社区按同一接口发布其它 kind。

### 与「不设开放插件市场」的关系

- **要：** 文档化 Core 接口 + entry point 发现 + 配置选型 + digest 锁定（**可分发插件**）。  
- **不要：** 远程商店默认信任、全局隐式启用、评测中热更新、插件改分或挂载 gold。  

流通方式可以是 `pip`、私有索引或 monorepo 子包；**信任来自 pin 与 grant，不来自商店评分**。
