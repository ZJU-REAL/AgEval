# 03 — 题包 `run.py` 与 SDK

题包入口是 **`run.py`**：`async def run(ctx: RunContext) -> RunTerminal`。可选 SDK 包名 `ageval-sdk`，import `ageval_sdk`。

SDK 可被 upstream 替代。**不**拥有 Run identity、盒子、credential、PASS。

## 负责 / 不负责

| 负责 | 禁止 |
| --- | --- |
| loop、角色、本地 Tool、`ctx.publish_json` / 可选 `ctx.publish_tree` | 最终 PASS |
| `ctx.agent.session(profile_id).invoke` | 持有 host 凭据 |
| 读 `ctx.params`、workspace | 再读一份「真配置」覆盖 lock |
| 返回 `completed` / `failed` | 自己提硬顶、按 bench 名分支 |
| 业务 Tool、handoff | `host.start` / `host.upload` / `host.stop`、`apt`、装 agent CLI、读 `evaluation/` |

控制面不 import 题包模块。worker 是控制面子进程；Agent 经 Parent Agent Service + `attach_stdio` 进盒子。盒子在 `run.py` 被调用前已经就绪（environment 相位已跑完 `start` + seed + `setup.sh`）。

## 最小形状

```python
from ageval_sdk import RunContext, RunTerminal

async def run(ctx: RunContext) -> RunTerminal:
    async with ctx.agent.session("solver", max_turns=1) as session:
        reply = await session.invoke(ctx.params["instruction"])
    ctx.publish_json("reply", {"ok": bool(reply.get("ok")), "text": reply.get("text") or ""})
    if not reply.get("ok"):
        return RunTerminal.failed(str(reply.get("error") or "invoke_failed"))
    return RunTerminal.completed("ok")
```

`RunTerminal.completed` **不是** PASS。

## SDK 表面

```python
from ageval_sdk import (
    Agent,
    AgentSession,
    RunContext,
    RunParameterView,
    RunScope,
    RunTerminal,
    Tool,
    ToolSet,
    AllowList,
    CallLimit,
)
```

| 对象 | 用途 |
| --- | --- |
| `RunContext` | params、workspace、artifact_dir、agent、publish |
| `RunTerminal` | `completed` / `failed`；不是 PASS |
| `Agent.session(profile_id)` | 经 unix socket 调 parent Agent Service |
| `ToolSet` / `CallLimit` | 题包软限，不替代 Runtime 硬顶 |

`AgentSession.record_observation` 是补充口：域工具由 `run.py` 执行后，把 observation 挂到刚结束的 invoke。parent 写入该 invoke 的 `events.jsonl`；record 相位折进 `trajectory.jsonl`。SDK **不**自己写 layer C。

`run.py` 通过 `ctx.agent.session(...).invoke` 调 Agent。ACP attach 发生在第一次 invoke。SDK 不拥有 `host.start`、凭据文件内容、final PASS。

evaluate 相位同样可以用 SDK：gold 已 upload 到 **打分 Host** 之后，`evaluator.py` 可以 `Agent.session(<role>).invoke`（role 须在同一份 `profiles.yaml` 里，且不得复用 solver 的 key locator）。这些 invoke 走同一 Parent Agent Service 与该 profile 的 executor。job `evaluate_host.isolated` 时 attach/exec 打打分 Host，不是 Agent 盒。密封进 `evaluation/observation.jsonl`，省略 `user` 行。`evaluator.py` **不得** bind PASS；仍返回 `{status, score, metrics}`。不调 `Agent.session` = 今日路径，无 observation 文件。invoke kwargs 仍不得改 `profile_id` / executor。SDK **仍然** 没有盒子动词。

`ctx.publish_tree(id, path)` 是可选登记：告诉 Runtime「这份 tree 已由 Agent 写在 workspace」。**拷贝与 exclude 仍归 harvest**，不在 SDK 里做。题包 yaml 已经声明 `kind: tree` 且 `path` 指向 Agent 写过的工作区时，`run.py` 不必再调。`publish_json` / `publish_file` 仍是单文件。登记成功不是 PASS。

## invoke 工具通道

`Agent.session(profile_id).invoke` 默认仍是今天的 **prompt-only** 文本调用。可选关键字（省略 = 旧行为）：

| 参数 | 含义 |
| --- | --- |
| `tools` | OpenAI 风格工具目录：`[{type: function, function: {name, description?, parameters}}]` |
| `messages` | 可选 chat 历史（`role` / `content`，以及后续 `tool` / `tool_calls` 轮） |

返回值在既有 `ok` / `text` / `structured` 之外，可以带结构化 **`tool_calls`**：`[{id, name, arguments}]`。`arguments` 是对象，不是 JSON 字符串。没有工具调用时该字段为空（省略或 `[]`），`text` 仍是助手文本。

约定：

- 题包把 **域工具目录** 交给 invoke；真正执行仍在 `run.py`（`ToolSet.call` 或 package `Environment.get_response`）。SDK / parent **不**代跑域工具，**不**把 MCP / home-files / skills 注册成可调用工具。
- `executor: acp` **忽略** `tools` / `messages`，继续文本 invoke。coding-agent 入口不变；ACP 不因为题包传了目录就要求 `tools=`。
- 禁止把 `profile_id` / workspace / executor 绑定从 invoke kwargs 里改掉。
- `tool_calls` 与 `RunTerminal.completed` 都不是 PASS。PASS 只来自独立 evaluator。

最小形状（openai-http 原生工具；ACP 路径可继续只传 prompt）：

```python
reply = await session.invoke(
    instruction,
    tools=catalog,          # 可选
    messages=history,       # 可选；省略则 parent 用 prompt 包一轮 user
)
for call in reply.get("tool_calls") or ():
    obs = await tools.call(call["name"], call["arguments"])
    await session.record_observation(
        str(call.get("id") or ""),
        content=str(obs),
        raw_output=obs,
        function_name=str(call.get("name") or ""),
        invocation_id=reply.get("invocation_id"),
    )
```

`record_observation` 不消耗 invoke 配额、不是 PASS。缺 session / invocation 则 fail-closed（`no_invocation` / `unknown_session`）。

## 薄 task

多题同构时，循环放 `shared/lib`，成员 `run.py` 只转发。gold 永不进 `shared/`。
