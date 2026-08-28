# Agent Service / ACP

两条 **独立** 的 coding-agent inlet，都占独占槽 `executor`。不要把第二条折进 ACP 插件，也不要写成 `executor: pi` / `executor: claude`。

`executor` 的独占赢家是 **每个 `agent_profiles` 一行一份**，不是 Attempt 上只许一个机制。同一 Attempt：solver 可以 `executor: acp`，judge 可以 `executor: openai-http`。`environment` 仍是 Attempt 级一份。两个插件仍不得抢**同一 profile graph** 上的 `executor`。lock 的 `extension_bindings` 按 profile id 各记一份。

| 赢家 | JSON-RPC client 在哪 | 环境 cap | 完成信号 |
| --- | --- | --- | --- |
| `executor: acp` | **parent 唯一** ACP client（`attach_stdio` 管子） | `attach_stdio` | ACP 帧（`stopReason`） |
| `executor: acp-oneshot` | **环境内** 一次性 client + ACP server | `exec` only | wrapper 进程退出 |

`executor: acp` 的规则不变：parent 是这条路径上**唯一**的 ACP JSON-RPC client。实现：`src/ageval/runtime/parent_agent.py` + `plugins/contrib/acp/`。结构约束见 [ARCHITECTURE.md](../../../ARCHITECTURE.md)。

## `executor: acp`（parent client）

```yaml
# profiles.yaml
environment: docker
agent_profiles:
  solver:
    executor: acp
    model: …
    api_key: ${ZHIPU_API_KEY}   # locator；值不进 lock
    options:
      entry: pi   # 或 codex / claude-code / opencode / grok-build
    extensions:
      - plugin: acp
      - plugin: docker   # 与 environment 赢家一致
```

ACP `inject: [service: environment]`（按服务名拿 host，**不**绑 `plugin_id: e2b`），要求 capability `attach_stdio`。缺则 lock 失败，不在 invoke 时探测管子。这是稳定接口：docker / e2b / ssh / daytona 都登记为同一个服务名；内部运输收在 `attach_stdio` 里。`exec` 是同一服务上的另一个方法（环境内一次性命令），不是第二 service。dsh / nooa inject `exec` / `upload`；`acp-oneshot` 只要 `exec`。三者都经 `host.exec` 跑环境内 worker，不得在 parent 里假定本机 POSIX 路径。环境没有 `attach_stdio` 时 **`executor: acp` 仍 lock 失败**；改走 `acp-oneshot`（或其它 exec 赢家），不是给 ACP 插件加 fallback。

```python
host = ctx.services.require("environment")
pipe = await host.attach_stdio(argv, placement=placement, env=child_env)
# JSON-RPC 走 pipe.stdin / pipe.stdout
```

Placement 无 `container_id`。ACP 禁止 import docker / e2b / daytona / ssh。`wrap_docker_exec` 缩进 docker 插件。`run_attempt` 也会把赢家放进 `ctx.host`；inject 是 lock 时的依赖声明。

不要写 `executor: pi` / `executor: codex`。entry 是 ACP / oneshot 的 `options.entry`，不是独占槽赢家。

## `executor: acp-oneshot`（环境内 oneshot client）

外置 `ageval.plugin/1`，`plugin_id: acp-oneshot`（机制名，不是产品名）。模式同 `plugins/miniswe/` / `plugins/dsh/`：parent 只 `host.exec`，不 `attach_stdio`。

```yaml
environment: docker   # 或任何声明 exec 的 kind
agent_profiles:
  solver:
    executor: acp-oneshot
    options:
      entry: pi   # 或 claude-code / opencode / …；与 ACP 同一组 id
    extensions: [acp-oneshot, docker]
```

1. `inject: { service: environment, capabilities: [exec] }`。缺 `exec` 则 lock 失败。**不要** `attach_stdio`。
2. 一次 `invoke` = 一次 `host.exec`。parent 把 entry 的 `acp_command`（来自 ACP entry 表）、prompt、cwd、模型绑定交给环境内 wrapper；等进程退出后解析 `AgentResult`。
3. wrapper 在环境内 spawn 该 entry 的 ACP stdio server，自己当一次性 client：`initialize` → `session/new` → `session/prompt`，permission RPC 与 `stopReason` 都留在环境内。默认 **不** 跨 `invoke` 复用 session。
4. `trajectory_collect` 映射 wrapper 写出的事件。Core **不** 刮 vendor CLI 日志。
5. entry 表与 ACP 共用 id（pi / claude-code / opencode / …）；本插件的 `execution_mode` 是 oneshot wrap，不是 `acp-stdio`。切厂商只改 `options.entry`。
6. 笛卡尔积：任何报 `exec` 的环境（docker / ssh B / e2b / 只提供 exec 的云 kind）。`executor: acp` 在没有 `attach_stdio` 的环境上仍然 lock 失败。

环境内 wrapper 是 stdlib JSON-RPC，**不是** 把 Python ACP SDK 装进 Attempt 镜像。SDK 仍只在 parent，且只服务 `executor: acp`。

无新 CLI flag。凭证仍是 locator，投影进 **exec** env（与 ACP 同一套 BYOK，不是 attach 管子）。空 job / 未装此插件 = 现行为。

## 调用链

```text
run.py / evaluator.py  Agent.session(profile).invoke
  → unix socket AGEVAL_AGENT_SERVICE_SOCK
  → ParentAgentService
       按该 profile 的 executor 赢家 invoke
       before_agent_invoke
       executor.invoke → host.attach_stdio(entry argv) 或 host.exec（环境内 worker）
                        或 openai-http POST /chat/completions
       after_agent_invoke
       normalize_agent_result
  → 层 C：run 相位 → trajectory.jsonl
           evaluate 相位 → evaluation/observation.jsonl（省略 user）
```

`ParentAgentService.invoke` 只回 `AgentResult`（含可选 `tool_calls`）。**不**在每次 invoke 后 `download` 环境内 workspace。轨迹来自 executor events。publishable 在 **solver writer 停后** 由 run 相位 harvest 一次（Protocol `download`；tree 按 exclude 做快照），evaluate 再把快照 upload 进 **打分 Host**。

Agent Service **跨 evaluate 保持**（或 reopen）：`evaluator.py` 才能 `Agent.session`。run 结束停的是 **solver writer**（该相位已打开的 profile 不得再 invoke），不是把整段服务拆掉再打分。gold 已经在打分 Host；solver 不得在 gold 之后 invoke。Attempt 结束（cleanup / `run_attempt` finally）才停服务。

## evaluate 相位的 attach 目标与环境内 socket

`executor: acp` 仍 `inject: [service: environment]`，parent 仍是唯一 JSON-RPC client。缺省（同一环境）attach 目标就是 run 那只 Host，与今日相同。

`evaluate_host.isolated: true` 时：

- `evaluator.py` 与 `run.py` 一样是 **parent 子进程**。`AGEVAL_AGENT_SERVICE_SOCK` 是本机 unix 路径，不 bind-mount 进容器。
- evaluate 相位的 `Agent.session`（judge 等 **未** 在 run 用过的 profile）走同一 Parent Agent Service。ACP `attach_stdio` 打 **打分 Host**（environment 服务在 evaluate 开头 rebound），不是 Agent Host。solver 仍密封。
- isolated 打分环境 start 之后，对上述 ACP profile 再跑 `after_environment_ready`（probe / 按 entry `install_command`）。不要把 solver 的 ACP 配方装进打分镜像。
- Agent 容器 **没有** docker daemon socket。ACP / `attempt` / `run.py` 仍然不见 `container_id`。

observe 这些 invoke：`evaluation/observation.jsonl`（省略 `user` 行）。不是 PASS。

ACP attach 发生在第一次 invoke，不是独立 phase。`acp-oneshot` 每次 invoke 都 exec 一次 wrapper，完成 = 该进程退出码 + 解析出的 `AgentResult`。Harness completed / 轨迹 / judge 输出 **不是** PASS。

Socket 帧可带 `tools` / `messages`（省略 = prompt-only）。parent 原样转给 executor；ACP 忽略这两项。`tool_calls` 回 worker。request.json / trajectory **只记 locator 与目录名，不记密钥**。

## openai-http 原生 tools

kind 名仍是 `openai-http`（api-client）。没有第二套 dialect、没有 Core 里的 LiteLLM、没有 Anthropic/Dashscope 直连——那些走 OpenAI-compatible gateway。

| | 行为 |
| --- | --- |
| 省略 `tools` | 今日路径：`messages: [{role: user, content: prompt}]`，读 `choices[0].message.content` |
| 题包传入 `tools` | POST body 带 `tools`；读 `choices[0].message.tool_calls` → `AgentResult.tool_calls` |
| `messages` | 若提供，作为 chat 历史（不再只包一轮 prompt） |
| capability | `tools: native`，`session: new-only`（逻辑 session，无 provider resume） |
| 凭证 | 一等字段 `model` / `base_url` / `api_key`（env locator）。远程 URL 缺钥 fail-closed。loopback 空钥是 **HTTP executor 规则**（`openai-http` / `dsh` / `nooa` / `miniswe`），不是 openai-http 特例 |
| `options.reasoning_effort` | 可选。有值则写入 Chat Completions 的 `reasoning_effort`；缺省不发该键。evidence：`locked_reasoning_effort` / `actual_reasoning_effort`（HTTP 200 时二者相同；4xx 时 actual 为 null） |

tau2-class harness（journeys `tau2-dialog-min`、`examples/tau3-*`）把域 schema 传入 invoke；收到 `tool_calls` 后走 package `Environment.get_response` / `ToolSet.call`，再 `record_observation` 把回包挂到该 invoke。原生 `tool_calls` 是 **openai-http 的主动作通道**；「Return ONLY JSON」只留给没有 `tool_calls` 的文本 executor（ACP）。禁止在 Core 里 scrape vendor stdout 当工具通道。

`openai-http` 的 executor events 用 Core 合同：`kind: tool` + `phase: start` + `tool_call_id` / `function_name` / `args`。环境观察是 `phase: update`（source `ageval`），不是 HTTP 响应的一部分。

`AgentResult.usage` 与层 C `terminal.usage` 同一形状（见 [evidence.md](evidence.md)）：一等 `prompt_tokens` / `completion_tokens` / `cached_tokens` / `cost_usd`（未知省略）。厂商 leftover 与插件袋在兄弟字段 `extra`。`openai-http` 从 HTTP `usage` 映射；ACP 从 `PromptResponse.usage` + `usage_update` 映射。缺 usage 就省略，不编造。usage / extra 是观察，不是 PASS。

## 凭证：BYOK / BYOA

两条，都不是整份 `os.environ`：

| | 含义 | 缺则 |
| --- | --- | --- |
| **BYOK** | 声明过的 API key env（`credential_env_names` / binding `api_key` locator）投影进环境 | fail-closed |
| **BYOA** | `keyless_auth`：allowlist copy 本机订阅 auth 文件进 attempt HOME，**不** mount 宿主 `$HOME` | 仅警告（OAuth / 本机登录 entry） |

子进程环境只投影 allowlist（`PATH` / `HOME` / `LANG`、entry 声明的 credential 名、binding 的 `api_key` / `base_url`、`fixed_env`）。宿主里未声明的 token 进不了 entry。

`--probe` / `ageval executors -v`：`credential_missing` 在需要密钥的 entry 上 fail-closed；keyless 只警告。HTTP executor 在锁定 `base_url` 为 loopback 且钥省略 / locator 为空时 **不** 报 `credential_missing`。

### HTTP loopback 空钥

`openai-http` / `dsh` / `nooa` / `miniswe` 共用一条 host-only 判断（`src/ageval/plugins/http_loopback.py`）：host 仅为 `127.0.0.1` / `localhost` / `::1`。不含 RFC1918、不含名字里碰巧带这些子串的 URL。

- loopback 且 `api_key` 省略或 locator env 为空 → invoke 继续（空 `Authorization` 或按该协议省略头）。
- 非 loopback 缺钥 → 仍 fail-closed。
- 不改 lock schema；locator **值**不进 lock / overlay / trajectory。ACP / `keyless_auth` 不动。

## Agent 运行时（挂 `after_environment_ready`）

1. 读 `options.entry`（如 `pi`）→ 需要哪些环境内二进制（`pi`、`pi-acp`、…）以及 entry 表钉死的包版本。
2. `host.exec` 探测三件事：名字（`which`）、钉死的 npm 包版本（`npm ls -g pkg@pin`）、一次便宜的 stdio JSON-RPC `initialize`（不是 `session/prompt`）。同名但协议不是 stdio ACP（例如只开 TCP 的旧 `opencode`）算未命中。
3. **三件都齐就跳过。** 任一不对再按 **ACP entry 自己的** `install_command` `exec`，装完再探一次。失败 = environment 相位失败。不把「怎么装 opencode」下放到 environment 插件。
4. 不把安装写进 task `setup.sh`。`setup.sh` 只本题依赖。
5. docker 官方基座已 bake 且版本+stdio 对得上时，探测命中；云上瘦镜像或 snapshot 里是错版本/错协议才会走到安装。invoke 禁止 `npm i` / 浮动 `npx`。

Python ACP SDK 只在 parent，不进 Attempt 镜像。

厂商私有格式翻译在进程外 ACP entry（Mode 1 shim / Mode 2 原生 / Mode 3 厂商包）。禁止在 Core 里再写 vendor stdout scrape。

batch 默认 auto-approve，不提权、不突破未投影路径。decision 进 evidence。

Pi：官方 registry `pi-acp`（npm `pi-acp`，桥 `pi --mode rpc`）。勿与反向桥 `pi-shell-acp` 混淆。

官方基座 `docker/attempt` 在 **build 期** bake-in 最低 entry 的 engine + ACP 入口（Mode 1 双装：codex/claude/**pi** + 各自 adapter）。
