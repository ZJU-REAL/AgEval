# Agent Service / ACP

两条 **独立** 的 coding-agent inlet，都占独占槽 `executor`。不要把第二条折进 ACP 插件，也不要写成 `executor: pi` / `executor: claude`。

| 赢家 | JSON-RPC client 在哪 | 盒子 cap | 完成信号 |
| --- | --- | --- | --- |
| `executor: acp` | **parent 唯一** ACP client（`attach_stdio` 管子） | `attach_stdio` | ACP 帧（`stopReason`） |
| `executor: acp-oneshot` | **盒内** 一次性 client + ACP server | `exec` only | wrapper 进程退出 |

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

ACP `inject: [service: environment]`（按服务名拿 host，**不**绑 `plugin_id: e2b`），要求 capability `attach_stdio`。缺则 lock 失败，不在 invoke 时探测管子。这是稳定接口：docker / e2b / ssh / daytona 都登记为同一个服务名；内部运输收在 `attach_stdio` 里。`exec` 是同一服务上的另一个方法（盒内一次性命令），不是第二 service。dsh / nooa inject `exec` / `upload`；`acp-oneshot` 只要 `exec`。三者都经 `host.exec` 跑盒内 worker，不得在 parent 里假定本机 POSIX 路径。盒子没有 `attach_stdio` 时 **`executor: acp` 仍 lock 失败**；改走 `acp-oneshot`（或其它 exec 赢家），不是给 ACP 插件加 fallback。

```python
host = ctx.services.require("environment")
pipe = await host.attach_stdio(argv, placement=placement, env=child_env)
# JSON-RPC 走 pipe.stdin / pipe.stdout
```

Placement 无 `container_id`。ACP 禁止 import docker / e2b / daytona / ssh。`wrap_docker_exec` 缩进 docker 插件。`run_attempt` 也会把赢家放进 `ctx.host`；inject 是 lock 时的依赖声明。

不要写 `executor: pi` / `executor: codex`。entry 是 ACP / oneshot 的 `options.entry`，不是独占槽赢家。

## `executor: acp-oneshot`（盒内 oneshot client）

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
2. 一次 `invoke` = 一次 `host.exec`。parent 把 entry 的 `acp_command`（来自 ACP entry 表）、prompt、cwd、模型绑定交给盒内 wrapper；等进程退出后解析 `AgentResult`。
3. wrapper 在盒内 spawn 该 entry 的 ACP stdio server，自己当一次性 client：`initialize` → `session/new` → `session/prompt`，permission RPC 与 `stopReason` 都留在盒内。默认 **不** 跨 `invoke` 复用 session。
4. `trajectory_collect` 映射 wrapper 写出的事件。Core **不** 刮 vendor CLI 日志。
5. entry 表与 ACP 共用 id（pi / claude-code / opencode / …）；本插件的 `execution_mode` 是 oneshot wrap，不是 `acp-stdio`。切厂商只改 `options.entry`。
6. 笛卡尔积：任何报 `exec` 的盒子（docker / ssh B / e2b / 只提供 exec 的云 kind）。`executor: acp` 在没有 `attach_stdio` 的盒子上仍然 lock 失败。

盒内 wrapper 是 stdlib JSON-RPC，**不是** 把 Python ACP SDK 装进 Attempt 镜像。SDK 仍只在 parent，且只服务 `executor: acp`。

无新 CLI flag。凭证仍是 locator，投影进 **exec** env（与 ACP 同一套 BYOK，不是 attach 管子）。空 job / 未装此插件 = 现行为。

## 调用链

```text
run.py  Agent.session(profile).invoke
  → unix socket AGEVAL_AGENT_SERVICE_SOCK
  → ParentAgentService
       before_agent_invoke
       executor.invoke → host.attach_stdio(entry argv) 或 host.exec（盒内 worker）
                        或 openai-http POST /chat/completions
       after_agent_invoke
       normalize_agent_result
  → 层 C：evidence 写 trajectory.jsonl
```

`ParentAgentService.invoke` 只回 `AgentResult`（含可选 `tool_calls`）。**不**在每次 invoke 后 `download` 盒内 workspace。轨迹来自 executor events。缺的 publishable 文件在 **writer 停后** 由 run 相位 harvest（Protocol `download`），evaluate 再把 `task-artifacts` upload 进盒。

ACP attach 发生在第一次 invoke，不是独立 phase。`acp-oneshot` 每次 invoke 都 exec 一次 wrapper，完成 = 该进程退出码 + 解析出的 `AgentResult`。Harness completed / 轨迹 **不是** PASS。

Socket 帧可带 `tools` / `messages`（省略 = prompt-only）。parent 原样转给 executor；ACP 忽略这两项。`tool_calls` 回 worker。request.json / trajectory **只记 locator 与目录名，不记密钥**。

## openai-http 原生 tools

kind 名仍是 `openai-http`（api-client）。没有第二套 dialect、没有 Core 里的 LiteLLM、没有 Anthropic/Dashscope 直连——那些走 OpenAI-compatible gateway。

| | 行为 |
| --- | --- |
| 省略 `tools` | 今日路径：`messages: [{role: user, content: prompt}]`，读 `choices[0].message.content` |
| 题包传入 `tools` | POST body 带 `tools`；读 `choices[0].message.tool_calls` → `AgentResult.tool_calls` |
| `messages` | 若提供，作为 chat 历史（不再只包一轮 prompt） |
| capability | `tools: native`，`session: new-only`（逻辑 session，无 provider resume） |
| 凭证 | 一等字段 `model` / `base_url` / `api_key`（env locator）。缺钥 fail-closed（loopback 空钥仅用于本机 mock） |

tau2-class harness（journeys `tau2-dialog-min`、`examples/tau3-*`）把域 schema 传入 invoke；收到 `tool_calls` 后走 package `Environment.get_response` / `ToolSet.call`。原生 `tool_calls` 是 **openai-http 的主动作通道**；「Return ONLY JSON」只留给没有 `tool_calls` 的文本 executor（ACP）。禁止在 Core 里 scrape vendor stdout 当工具通道。

## 凭证：BYOK / BYOA

两条，都不是整份 `os.environ`：

| | 含义 | 缺则 |
| --- | --- | --- |
| **BYOK** | 声明过的 API key env（`credential_env_names` / binding `api_key` locator）投影进盒 | fail-closed |
| **BYOA** | `keyless_auth`：allowlist copy 本机订阅 auth 文件进 attempt HOME，**不** mount 宿主 `$HOME` | 仅警告（OAuth / 本机登录 entry） |

子进程环境只投影 allowlist（`PATH` / `HOME` / `LANG`、entry 声明的 credential 名、binding 的 `api_key` / `base_url`、`fixed_env`）。宿主里未声明的 token 进不了 entry。

`--probe` / `ageval executors -v`：`credential_missing` 在需要密钥的 entry 上 fail-closed；keyless 只警告。

## Agent 运行时（挂 `after_environment_ready`）

1. 读 `options.entry`（如 `pi`）→ 需要哪些盒内二进制（`pi`、`pi-acp`、…）以及 entry 表钉死的包版本。
2. `host.exec` 探测三件事：名字（`which`）、钉死的 npm 包版本（`npm ls -g pkg@pin`）、一次便宜的 stdio JSON-RPC `initialize`（不是 `session/prompt`）。同名但协议不是 stdio ACP（例如只开 TCP 的旧 `opencode`）算未命中。
3. **三件都齐就跳过。** 任一不对再按 **ACP entry 自己的** `install_command` `exec`，装完再探一次。失败 = environment 相位失败。不把「怎么装 opencode」下放到 environment 插件。
4. 不把安装写进 task `setup.sh`。`setup.sh` 只本题依赖。
5. docker 官方基座已 bake 且版本+stdio 对得上时，探测命中；云上瘦镜像或 snapshot 里是错版本/错协议才会走到安装。invoke 禁止 `npm i` / 浮动 `npx`。

Python ACP SDK 只在 parent，不进 Attempt 镜像。

厂商私有格式翻译在进程外 ACP entry（Mode 1 shim / Mode 2 原生 / Mode 3 厂商包）。禁止在 Core 里再写 vendor stdout scrape。

batch 默认 auto-approve，不提权、不突破未投影路径。decision 进 evidence。

Pi：官方 registry `pi-acp`（npm `pi-acp`，桥 `pi --mode rpc`）。勿与反向桥 `pi-shell-acp` 混淆。

官方基座 `docker/attempt` 在 **build 期** bake-in 最低 entry 的 engine + ACP 入口（Mode 1 双装：codex/claude/**pi** + 各自 adapter）。
