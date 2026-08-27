# Environment（盒子）

独占槽 `environment`。Protocol 在 `src/ageval/environments/protocol.py`，无厂商 SDK。结构总图与 locality 规则见 [ARCHITECTURE.md](../../../ARCHITECTURE.md)。动词与 Placement 形状见 [01](../01-ageval-core.md)。

盒内路径合同：`/attempt/workspace`、`/attempt/home`、`/attempt/artifacts`、`/attempt/evaluation`。

job 文档：

```yaml
# profiles.yaml — 选独占槽 environment 的赢家
format: ageval.profiles/1
environment: e2b    # local | docker | e2b | ssh | daytona
# environment_options:   # docker：image / platform / network / user / egress
#                        # ssh：host / user / port / key_env / image
#                        # daytona：image / snapshot / timeout_seconds
# evaluate_host:         # 省略 = 同盒打分
#   isolated: true       # 第二只 EnvironmentProvider；不是新槽
```

取消隔离档产品面。不要写 `provider.kind`、`assurance: l0/l1`。Result 记 `kind` + `capabilities_used`。

## kind 与能力

`requires ∩ capabilities`：task `requires.environment` 缺省为空；非空必须 ⊆ kind.capabilities，否则 lock 失败。不能兑现的 cap 不许报 yes。

| cap | local | docker | e2b | ssh | daytona |
| --- | --- | --- | --- | --- | --- |
| exec / upload / download | yes | yes | yes | yes | yes |
| attach_stdio | 本机进程 | `docker exec -i` | **yes**（SDK 双向 stdin 流；旧 envd 在 start 探针失败） | ssh / 远端 docker exec | **yes**（session stdin + `suppress_input_echo`，泵到 `fileno()`；实现期 ACP `initialize` 握手成功。不是每次 start / `--probe` 再测） |
| uid_gid / path_views | no | yes | 通常 no | 通常 no | no |
| compose | no | yes | no | 视远端而定，默认 no | no |

`path_views` 仅 docker 一类能做 per-actor mount+UID。gold 默认隔离 **不依赖** 它（evaluate 晚上传）。要 compose 而 kind 没有该 cap → lock 失败。

`environment/Dockerfile`（或 `docker_image`）对 docker 与 e2b 是同一配方。docker 本机编；e2b `Template.from_dockerfile` 再 `Sandbox.create`。daytona 把同一配方编成 **snapshot**（`Image.from_dockerfile` 或公开 OCI tag），再 `Sandbox.create` from snapshot。OCI tag 须带具体 tag/digest；Daytona 拒绝 `latest` / `lts` / `stable`。

官方基座由 `docker/attempt/` 构建。题包 Dockerfile 用 `FROM ageval-attempt:base`。invoke 时禁止 `npm i` / 浮动 `npx`。Python ACP SDK 只在 parent，不进 Attempt 镜像。

docker `environment_options`：

- `image` / `docker_image` — 已有 tag，跳过本机构建
- `platform` — 缺省跟本机
- `network` — 缺省 `bridge`。这是 **原始 docker 网络名**。`none` 也是原始名：它会一并挡住盒内进程访问模型 API，**不是**下面的 LLM egress 模式。
- `egress` — 省略 = 今日 `bridge`。`egress: llm`（Current：仅 docker contrib）：Agent 盒出站 HTTP(S) 只能到达已绑定 profile 的 `base_url` 主机（parent 侧代理 + 盒内 `HTTPS_PROXY` / `HTTP_PROXY`，或等价物）。ACP stdio 仍是 parent `attach_stdio`，不走这条代理。不能兑现的 kind 写了该键 → lock 失败。依赖仍 bake 在题包 `environment/Dockerfile`；官方基座 invoke 时禁止 `npm i` / 浮动 `npx`。
- `user` — 盒内身份，`docker run --user` 与 `exec`/`attach_stdio` 同一值。缺省 `10001:10001`。`root` / `0` / `0:0` 开 root（Harbor 式终端题要 `apt` 或写 `/usr/local` 时用）。其它值必须是 `uid` 或 `uid:gid`。未知字符串一次失败。默认仍带 `no-new-privileges`。

`egress` 约束的是 **Agent 盒**。打分 Host 不继承该键，除非以后另开开关。

## 第二只盒子（evaluate，opt-in）

`environment` 独占槽仍一份赢家。`evaluate_host.isolated: true` 时 Runtime 再 `start` **同一个赢家类** 的第二实例：

- 配方：题包 `environment/evaluate.Dockerfile`，或 `evaluation.docker_image`。与 Agent 的 `environment/Dockerfile` 不是同一文件。Current 只要求 docker。
- work root **独立**（另一份 `BoxSpec.attempt_root`）。禁止把 Agent 的 bind-mount 或 live workspace symlink 进打分盒。
- 不加入 Agent compose 网络。compose 侧车仍随 Agent `host.start()` 起来，寿命与 Agent 盒相同；不要拿侧车当打分镜像。
- **禁止**把 docker daemon socket 挂进 **Agent** 盒。打分盒也不挂 daemon socket。locator 只给 parent 的 docker CLI。
- gold、tree/file 快照、`evaluator.py` 只 upload 到打分实例。Parent Agent Service 的 unix socket 在 evaluate 时 bind-mount 进 **打分** 容器（见 [agent-service](agent-service.md)），不在整段 Attempt 挂进 Agent 容器。
- cleanup 先停打分实例再停 Agent 实例（或并行，但两个都要停）。`keep_workspace` 只保留引擎声明要留的 work root，不得把第二盒的盘并回 Agent 盘。

不能再起第二盒的 kind（Current：`local` 以及尚未兑现的云 kind）遇到 `isolated: true` → lock 失败。不要为此发明 cap 名。

## `attach_stdio`

在**已开的盒**里再起一个前台进程，把 stdin/stdout 交回 parent。ACP 只拿 `StdioTransport`，不写 `if docker`。

| 赢家 | `attach_stdio(argv)` 内部 |
| --- | --- |
| local | 本机 `Popen(argv)` |
| docker | `Popen(["docker","exec","-i", …, *argv])`（旧 `wrap_docker_exec` 缩进此插件） |
| ssh **A** 盒子=整机 | `Popen(["ssh","-T", …, "--", *argv])`，agent 就是这台 VM 上的进程 |
| ssh **B** 盒子=远端容器 | `start()` 远端 `docker run` 已有 tag；`attach_stdio` = `ssh -- docker exec -i <cid> argv` |
| e2b | SDK 双向流（`stdin=True` + send stdin）。只跑完收 stdout 不够 ACP |
| daytona | **yes**。`create_session` + async session command + `send_session_command_input`（`suppress_input_echo`），stdout 用 HTTP logs 泵到 `os.pipe()`。未回退 PTY。kind 常量，之后不再探测 |

两种 ssh **agent 都在云上**。差别是隔离单元：整机 vs 机上容器。options：无 `image` → A；有已有 tag → B。`stop(delete=False)` 默认不 terminate 云主机。密钥 locator 不进 lock。

缺 `E2B_API_KEY` / `DAYTONA_API_KEY` / ssh locator：preflight 一次失败，不建 sandbox、不开远端容器。`--probe` 必须 `ready: false` 且未 start。`--probe` **不**发现 stdio。

E2B 模板 alias/hash 只在 `plugins/contrib/e2b`。Daytona snapshot 名 / sandbox id 只在 `plugins/contrib/daytona`。Core 只调 `host.start()`。

## daytona

独占赢家 `plugin_id: daytona`，first-party，与 e2b 同 locality。厂商 SDK 不得漏进 ACP / `attempt` / `run.py`。

Locator：`DAYTONA_API_KEY`（接受 `daytona_api_key`）。缺钥或缺 SDK import → 一次 `environment_preflight_failed`。

`environment_options`：

- `snapshot` — 已有 Daytona snapshot 名，跳过编 snapshot
- `image` — 公开 OCI tag/digest（禁止 `latest` / `lts` / `stable`）
- `timeout_seconds` — sandbox 寿命（映射 Daytona `auto_stop_interval`，分钟向上取整；默认 900）

无 `snapshot` 时：有 `image` 则 snapshot-from-OCI；否则用题包 `environment/Dockerfile`（`Image.from_dockerfile`）。snapshot 名按配方 digest 复用。盒内路径仍是 `/attempt/workspace` 等。

`attach_stdio` 是 kind 常量，与 e2b 一样。实现期用真钥在 session stdin 上完成 ACP `initialize`（echo fixture，干净 JSON，无 TTY echo）。因此 `executor: acp` + `environment: daytona` lock 成功。缺钥的 skip 不是这条 cap 的证据。

## ssh A / B

ssh A / B 由 `environment_options.image` 是否为空决定。host/user/`key_env` 是 locator，preflight 解析，不进 lock 明文密钥。

ACP 挂 `after_environment_ready`：名字 + 钉死包版本 + 一次 stdio `initialize`，不对再按 ACP entry 的 `install_command` 装。云镜像已 bake 且版本/协议对得上时探测命中，不得再装一遍。同名但不是 stdio ACP 的二进制不算命中。

## locality

executor **inject** 名为 `environment` 的服务（独占赢家自动 export 该名），lock 时核 capabilities。`executor: acp` 要 `attach_stdio`；盒内 worker（dsh / nooa / `acp-oneshot`）要 `exec`。调用只打 Protocol 方法。`exec` 不是独立 service。

```text
ACP / acp-oneshot / dsh / nooa  invoke
        │  inject service: environment
        │  只看见 Protocol（attach_stdio / exec / upload）
        ▼
contrib/docker   → docker exec / compose / uid_gid / path_views
contrib/e2b      → e2b SDK、template alias
contrib/daytona  → Daytona SDK、snapshot 名、sandbox id
contrib/ssh      → ssh A/B、远端 docker
contrib/local    → 本机目录
```

`docker exec` 只在 `plugins/contrib/docker/`。ACP 禁止 import docker/e2b/daytona/ssh。`attempt` / `run.py` 不见 `container_id`、不见 `if kind == e2b`。换 kind 不必改 executor 源码。

`run.py` 是 parent 子进程。seed 在 launch 投影到 `ctx.workspace_root`（local/docker 即共享盘；ssh/e2b/daytona 是 evidence 上的 seed 拷贝）。Agent Service **不**在每次 invoke 后 `download` workspace。writer 停后 runtime 按题包 `artifacts.publishable` harvest **一次**：`kind` 省略/`file` 收缺的单文件（盒内 `/attempt/workspace/<basename>` → parent `task-artifacts/`）；`kind: tree` 按 `exclude` 把工作区树拷成 evidence 上的不可变快照。共享盘上 `run.py` 已从磁盘 `publish_json` 的 file 跳过；远程盒走 Protocol `download`。tree 在 docker 上读已有 bind-mount 再拷，不要三次 export。搬哪些由题包声明，不写 `if kind`。聊天文本不是 Terminal 类题的权威产物，不得 publish 成功并挡住 harvest。evaluate 消费快照拷贝，不是 Agent 活目录。

## setup.sh 与侧车

`setup.sh` 是 environment **末槽** `environment_setup`，不是独立 provision phase。无文件则 no-op。失败是 environment 相位失败。重依赖进 Dockerfile，不要在 `run.py` 里 `apt`。

侧车：拆掉 Environment Manager。compose 或 `host.exec(service=)`。`run.py` 读投影 DSN。旧 `setup_steps` 废止。

## Current vs Target

| 项 | Current | Target（未宣称完成） |
| --- | --- | --- |
| local / docker | 公开真 `ageval run`（core ACP、journeys 点名题） | — |
| e2b / ssh / daytona | 代码在；缺钥 `--probe` fail-closed | 有凭证时同一题公开 `ageval run`（ssh 含 A+B） |
| Protocol seam | docker 已是真实赢家 | 第二个云赢家（e2b **或** ssh）真跑后 seam 才算成立 |

默认 CI **无**真 E2B/SSH/Daytona。skip ≠ 通过。不得从 docker 一次 PASS 推导 `isolated`。
