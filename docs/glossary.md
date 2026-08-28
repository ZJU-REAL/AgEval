# ageval Glossary

定义以 [design/](design/) 为准。

| 术语 | 定义 |
| --- | --- |
| **ageval** | 产品名（agent eval）。CLI / 包 / format 硬切 |
| **dataset** | 规范交付单位：根 `ageval.yaml`（`ageval.dataset/1`）+ `tasks/<id>/`。不是 SQL |
| **task** | dataset 成员：`task.yaml` + `run.py` + `evaluator.py` + 可选 `environment/` |
| **profiles.yaml** | job 文档：`environment` 赢家 + 角色绑定。`--agent` 与 `--profiles` 互斥。`--model` 改这次 run 的 `binding.model` |
| **Agent 包** | format `ageval.agent/1`。身份是 harness（executor / entry / overlays）；`binding.model` 是缺省 |
| **Run / Trial / Attempt** | Run = 一次 CLI 顶层；Trial = 一题 × 一套 profile（lock digest）；Attempt = 一次外层执行（失败重试 = 新 Attempt） |
| **Campaign** | 矩阵展开的多 Trial（`ageval campaign`） |
| **suite** | 一份 dataset 去掉 `--task` 的全成员跑。suite 指标是观测，不是 suite PASS |
| **run.py** | 题包 run phase 入口（`async def run(ctx)`）。不可读 `evaluation/` |
| **evaluator.py** | 题包打分；PASS 只从 evaluate 相位绑定进入。可选 `Agent.session`（LLM-as-judge）；观察不是 PASS |
| **RunTerminal** | 题包结束信号；`completed` ≠ PASS |
| **phase** | attempt 上的一大步（environment / run / evaluate / record / cleanup） |
| **独占槽** | 每个 resolved graph 一个赢家；登记为同名 service。`environment` 是 Attempt 级一份；`executor` 按 profile 各绑一份 |
| **链槽** | phase 内钩子，handler `(ctx, value, nxt)` |
| **environment**（槽） | 环境赢家：`local` / `docker` / `e2b` / `ssh` / `daytona`，同一 Protocol |
| **executor**（槽） | 该 `agent_profiles` 行的 Agent 后端赢家。coding-agent 默认 `acp`（parent client + `attach_stdio`）；`acp-oneshot` 是环境内一次性 client + `exec`。同一 Attempt 上不同 profile 可选不同机制 |
| **acp-oneshot** | 外置 executor 插件：parent 一次 `host.exec` 跑环境内 ACP server+client；不要求 `attach_stdio` |
| **service / inject** | 按名取能力：独占赢家以槽名 export；调用方 inject 服务名 + capabilities；lock 期解析。`exec` 是 Protocol 方法，不是独立 service |
| **attach_stdio** | host 在已开环境里起前台进程并交回 stdin/stdout |
| **ACP entry** | `options.entry`：`pi` / `codex` / `claude-code` / `opencode` / `grok-build` |
| **BYOK** | 声明过的 API key env 投影进环境；缺则 fail-closed |
| **BYOA** | `keyless_auth`；allowlist copy 本机 auth 文件进 attempt HOME |
| **capabilities** | kind 声明能兑现什么；lock 期 `requires ⊆ capabilities` |
| **path_views** | 同时多角色不同盘（mount+UID），仅 docker 类能兑现。gold 隔离不靠它 |
| **environment_setup** | environment 末槽；有 `setup.sh` 才 exec |
| **ssh A / ssh B** | A 环境=整机；B 环境=远端已有容器。同一 kind 的两种 options |
| **gold** | `tasks/*/evaluation/`。evaluate 开头再 upload |
| **composition root** | `application/composition.py`；CLI 只 import 它 |
| **LockedTaskConfig** | lock 产物与其 digest（含 `extension_bindings`） |
| **ageval SDK** | `RunContext` / `RunTerminal` / `Agent.session`。不拥有 identity / credential / PASS |
| **硬顶** | 执行前上限。事后 token 只是观测 |
| **evidence** | `.ageval/runs/<id>/`；布局字符串只在 `evidence/` 模块 |
| **轨迹** | `trajectory.jsonl`；复盘用，不能发明 PASS |

## format

| format |
| --- |
| `ageval.dataset/1` |
| `ageval.task/1` |
| `ageval.plugin/1` |
| `ageval.profiles/1` |
| `ageval.agent/1` |
| `ageval.trajectory.event/1` |

未知 format：一个错误，停。
