# Agent Service / ACP

parent **唯一** ACP JSON-RPC client。实现：`src/ageval/runtime/parent_agent.py` + `plugins/contrib/acp/`。结构约束见 [ARCHITECTURE.md](../../../ARCHITECTURE.md)。

coding-agent inlet：

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

ACP `inject: [service: environment]`（按服务名拿 host，**不**绑 `plugin_id: e2b`），要求 capability `attach_stdio`。缺则 lock 失败，不在 invoke 时探测管子。这是稳定接口：docker / e2b / ssh 都登记为同一个服务名；内部运输收在 `attach_stdio` 里。`exec` 是同一服务上的另一个方法（盒内一次性命令），不是第二 service。dsh / nooa 应 inject `exec` / `upload`，经 `host.exec` 跑盒内 worker，不得在 parent 里假定本机 POSIX 路径。

```python
host = ctx.services.require("environment")
pipe = await host.attach_stdio(argv, placement=placement, env=child_env)
# JSON-RPC 走 pipe.stdin / pipe.stdout
```

Placement 无 `container_id`。ACP 禁止 import docker / e2b / ssh。`wrap_docker_exec` 缩进 docker 插件。`run_attempt` 也会把赢家放进 `ctx.host`；inject 是 lock 时的依赖声明。

不要写 `executor: pi` / `executor: codex`。entry 是 ACP 选项，不是独占槽赢家。

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

ACP attach 发生在第一次 invoke，不是独立 phase。

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

1. 读 `options.entry`（如 `pi`）→ 需要哪些盒内二进制（`pi`、`pi-acp`、…）。
2. `host.exec` 探测：`command -v` / `which`。
3. **齐了就跳过。** 缺了再按 entry 的安装配方 `exec`（官方安装脚本 / 镜像内包管理器）。失败 = environment 相位失败。
4. 不把安装写进 task `setup.sh`。`setup.sh` 只本题依赖。
5. docker 官方基座已 bake entry 时，探测命中，云上瘦镜像才会走到安装。invoke 禁止 `npm i` / 浮动 `npx`。

Python ACP SDK 只在 parent，不进 Attempt 镜像。

厂商私有格式翻译在进程外 ACP entry（Mode 1 shim / Mode 2 原生 / Mode 3 厂商包）。禁止在 Core 里再写 vendor stdout scrape。

batch 默认 auto-approve，不提权、不突破未投影路径。decision 进 evidence。

Pi：官方 registry `pi-acp`（npm `pi-acp`，桥 `pi --mode rpc`）。勿与反向桥 `pi-shell-acp` 混淆。

官方基座 `docker/attempt` 在 **build 期** bake-in 最低 entry 的 engine + ACP 入口（Mode 1 双装：codex/claude/**pi** + 各自 adapter）。
