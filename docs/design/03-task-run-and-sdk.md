# 03 — 题包 `run.py` 与 SDK

题包入口是 **`run.py`**：`async def run(ctx: RunContext) -> RunTerminal`。可选 SDK 包名 `ageval-sdk`，import `ageval_sdk`。

SDK 可被 upstream 替代。**不**拥有 Run identity、盒子、credential、PASS。

## 负责 / 不负责

| 负责 | 禁止 |
| --- | --- |
| loop、角色、本地 Tool、`ctx.publish_json` | 最终 PASS |
| `ctx.agent.session(profile_id).invoke` | 持有 host 凭据 |
| 读 `ctx.params`、workspace | 再读一份「真配置」覆盖 lock |
| 返回 `completed` / `failed` | 自己提硬顶、按 bench 名分支 |
| 业务 Tool、handoff | `host.start`、`apt`、装 agent CLI、读 `evaluation/` |

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

`ctx.events` 只是补充。权威轨迹由 parent 写入 `trajectory.jsonl`。

`run.py` 通过 `ctx.agent.session(...).invoke` 调 Agent。ACP attach 发生在第一次 invoke。SDK 不拥有 `host.start`、凭据文件内容、final PASS。

## 薄 task

多题同构时，循环放 `shared/lib`，成员 `run.py` 只转发。gold 永不进 `shared/`。
