# Environment（盒子）

独占槽 `environment`。Protocol 在 `src/ageval/environments/protocol.py`，无厂商 SDK。结构总图与 locality 规则见 [ARCHITECTURE.md](../../../ARCHITECTURE.md)。动词与 Placement 形状见 [01](../01-ageval-core.md)。

盒内路径合同：`/attempt/workspace`、`/attempt/home`、`/attempt/artifacts`、`/attempt/evaluation`。

job 文档：

```yaml
# profiles.yaml — 选独占槽 environment 的赢家
format: ageval.profiles/1
environment: e2b    # local | docker | e2b | ssh
# environment_options:   # ssh：host / user / port / key_env / image
```

取消隔离档产品面。不要写 `provider.kind`、`assurance: l0/l1`。Result 记 `kind` + `capabilities_used`。

## kind 与能力

`requires ∩ capabilities`：task `requires.environment` 缺省为空；非空必须 ⊆ kind.capabilities，否则 lock 失败。不能兑现的 cap 不许报 yes。

| cap | local | docker | e2b | ssh |
| --- | --- | --- | --- | --- |
| exec / upload / download | yes | yes | yes | yes |
| attach_stdio | 本机进程 | `docker exec -i` | **yes**（SDK 双向 stdin 流；旧 envd 在 start 探针失败） | ssh / 远端 docker exec |
| uid_gid / path_views | no | yes | 通常 no | 通常 no |
| compose | no | yes | no | 视远端而定，默认 no |

`path_views` 仅 docker 一类能做 per-actor mount+UID。gold 默认隔离 **不依赖** 它（evaluate 晚上传）。要 compose 而 kind 没有该 cap → lock 失败。

`environment/Dockerfile`（或 `docker_image`）对 docker 与 e2b 是同一配方。docker 本机编；e2b `Template.from_dockerfile` 再 `Sandbox.create`。

官方基座由 `docker/attempt/` 构建。题包 Dockerfile 用 `FROM ageval-attempt:base`。invoke 时禁止 `npm i` / 浮动 `npx`。Python ACP SDK 只在 parent，不进 Attempt 镜像。

## `attach_stdio`

在**已开的盒**里再起一个前台进程，把 stdin/stdout 交回 parent。ACP 只拿 `StdioTransport`，不写 `if docker`。

| 赢家 | `attach_stdio(argv)` 内部 |
| --- | --- |
| local | 本机 `Popen(argv)` |
| docker | `Popen(["docker","exec","-i", …, *argv])`（旧 `wrap_docker_exec` 缩进此插件） |
| ssh **A** 盒子=整机 | `Popen(["ssh","-T", …, "--", *argv])`，agent 就是这台 VM 上的进程 |
| ssh **B** 盒子=远端容器 | `start()` 远端 `docker run` 已有 tag；`attach_stdio` = `ssh -- docker exec -i <cid> argv` |
| e2b | SDK 双向流（`stdin=True` + send stdin）。只跑完收 stdout 不够 ACP |

两种 ssh **agent 都在云上**。差别是隔离单元：整机 vs 机上容器。options：无 `image` → A；有已有 tag → B。`stop(delete=False)` 默认不 terminate 云主机。密钥 locator 不进 lock。

缺 `E2B_API_KEY` / ssh locator：preflight 一次失败，不建 sandbox、不开远端容器。`--probe` 必须 `ready: false` 且未 start。

E2B 模板 alias/hash 只在 `plugins/contrib/e2b`。Core 只调 `host.start()`。

## ssh A / B

ssh A / B 由 `environment_options.image` 是否为空决定。host/user/`key_env` 是 locator，preflight 解析，不进 lock 明文密钥。

ACP 挂 `after_environment_ready`：先 `which`，缺再装。云镜像已 bake entry 时探测命中，不得再装一遍。

## locality

executor **inject** 名为 `environment` 的服务（独占赢家自动 export 该名），lock 时核 capabilities。`executor: acp` 要 `attach_stdio`；盒内 worker（dsh / nooa / `acp-oneshot`）要 `exec`。调用只打 Protocol 方法。`exec` 不是独立 service。

```text
ACP / acp-oneshot / dsh / nooa  invoke
        │  inject service: environment
        │  只看见 Protocol（attach_stdio / exec / upload）
        ▼
contrib/docker  → docker exec / compose / uid_gid / path_views
contrib/e2b     → e2b SDK、template alias
contrib/ssh     → ssh A/B、远端 docker
contrib/local   → 本机目录
```

`docker exec` 只在 `plugins/contrib/docker/`。ACP 禁止 import docker/e2b/ssh。`attempt` / `run.py` 不见 `container_id`、不见 `if kind == e2b`。换 kind 不必改 executor 源码。

`run.py` 是 parent 子进程。seed 在 launch 投影到 `ctx.workspace_root`（local/docker 即共享盘；ssh/e2b 是 evidence 上的 seed 拷贝）。Agent Service **不**在每次 invoke 后 `download` workspace。writer 停后 runtime 按 `artifacts.publishable` 收 **缺的** 文件：盒内 `/attempt/workspace/<basename>` → parent `task-artifacts/`。共享盘上 `run.py` 已 `publish_json` 的跳过；ssh/e2b 走 Protocol `download`。搬哪些由题包声明，不写 `if ssh`。聊天文本不是 Terminal 类题的权威产物。

## setup.sh 与侧车

`setup.sh` 是 environment **末槽** `environment_setup`，不是独立 provision phase。无文件则 no-op。失败是 environment 相位失败。重依赖进 Dockerfile，不要在 `run.py` 里 `apt`。

侧车：拆掉 Environment Manager。compose 或 `host.exec(service=)`。`run.py` 读投影 DSN。旧 `setup_steps` 废止。

## Current vs Target

| 项 | Current | Target（未宣称完成） |
| --- | --- | --- |
| local / docker | 公开真 `ageval run`（core ACP、journeys 点名题） | — |
| e2b / ssh | 代码在；缺钥 `--probe` fail-closed | 有凭证时同一题公开 `ageval run`（ssh 含 A+B） |
| Protocol seam | docker 已是真实赢家 | 第二个云赢家（e2b **或** ssh）真跑后 seam 才算成立 |

默认 CI **无**真 E2B/SSH。skip ≠ 通过。不得从 docker 一次 PASS 推导 `isolated`。
