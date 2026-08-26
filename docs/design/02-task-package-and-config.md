# 02 — dataset 与配置

交付单位是 **dataset**（根配置 + 若干 task 成员），不是 SQL。侧车 Postgres 仍叫 compose service。lock 数据流见 [ARCHITECTURE.md](../../ARCHITECTURE.md) § Data Flow。

## 根

```yaml
format: ageval.dataset/1
dataset_id: example/journeys
version: "0.1.0"
tasks:
  root: tasks
```

文件名 `ageval.yaml`。未知 format lock 失败：`invalid_format` 于 `/format`。

CLI 路径永远是 dataset 根：

```bash
ageval lock examples/journeys --task terminal-jsonl-agg
ageval run  examples/journeys --task terminal-jsonl-agg
ageval tasks examples/journeys
ageval run  official/demo@0.1.0 --dir tmp
```

`run` / `lock` / `view` / `results upload-suite` 第一个参数是本地 dataset 根 **或** Hub ref（`dataset_id@version` / `@sha256:…`）。`--dir <path>` 只在 `run` 上、且只配合 Hub ref：在 `<path>/<dataset_id>/` 找包（例：`--dir tmp` + `official/demo@0.1.0` → `tmp/official/demo`）。子目录已是匹配 dataset 就复用，否则 fetch 进去再 run。相对路径相对 cwd。本地路径再加 `--dir` 是 `invalid_override`。`lock` / `view` / `upload-suite` 走已校验缓存，命中不打 Hub。`tasks` / `campaign` 仍只收本地目录。

`--profiles` 整份替换根上的 job 文档。`--agent` 与 `--profiles` 互斥。`--set` 白名单：`/parameters/seed`、`/parameters/active_profile`、`/bindings/<role>/{model,executor,api_key,base_url,options/<key>}`。`limits.*` 不可 `--set`。

## 成员 `task.yaml`

```yaml
format: ageval.task/1
task_id: acp-local-min
parameters:
  instruction: "…"
agent_profiles:
  - id: solver
limits:
  wall_time_seconds: 600
  agent_invocations: 1
artifacts:
  publishable:
    - id: reply
      path: artifacts/reply.json
evaluation:
  inputs:
    - artifact: reply
      target: artifacts/reply.json
```

## 薄 task 目录

```text
tasks/<id>/
  task.yaml                 # 只写例外；目录名 == task_id == --task
  run.py                    # async def run(ctx) — 仅 run phase
  evaluator.py              # 仅 evaluate
  environment/
    Dockerfile              # 有则用；docker 与 e2b 同一配方
    setup.sh                # 有则 environment_setup 去 exec
  data/                     # Agent 可见 seed；environment 相位 upload 到 /attempt/workspace
  evaluation/               # gold；agent 不可见；evaluate 开头才 upload
```

**缺省（有文件就认，不必在 yaml 再写一遍）：**

| 没写时 | 默认 |
| --- | --- |
| run 入口 | 存在 `run.py` → `run:run` |
| evaluator 入口 | 存在 `evaluator.py` → `evaluator:evaluate` |
| 镜像配方 | 存在 `environment/Dockerfile` → 用之；或 yaml `docker_image` |
| setup | 存在 `environment/setup.sh` → `environment_setup` exec；没有则跳过 |
| `requires.environment` | 空 = 不额外要 cap |
| seed | 存在 `data/` → environment 相位 upload |
| gold | 存在 `evaluation/` → evaluate 相位 upload |

yaml 显式字段覆盖缺省。旧 `harness.entrypoint` 与未知 format **拒绝**，不映射。

不要：`provider.kind`、`assurance`、`harness:` 块、角色上的 `executor` / `api_key`（那些在 profiles）。

`run.py` **禁止**：`host.start`、`apt`、装环境、读 `evaluation/`。只做 session / invoke / 业务 Tool。盒子在它被调用前已经就绪。ACP attach 发生在第一次 invoke。

多题同构时，循环放 `shared/lib`，成员 `run.py` 只转发。gold 永不进 `shared/`。Runtime 注入 path 前缀是 `[task_dir, dataset_root]`，不会把 `shared/lib` 叶子再塞进 path。docker 镜像 **不会** 由 Core 隐式 COPY `shared/`；容器内要用时在 Dockerfile 里显式 `COPY`，并把 dataset 根放进 `PYTHONPATH`。

## job `profiles.yaml`

```yaml
format: ageval.profiles/1
environment: local          # 或 docker / e2b / ssh / daytona
# environment_options:      # docker：image / platform / network / user（`root` 开 root）
#                           # ssh：host / user / port / key_env / image
#                           # daytona：image / snapshot / timeout_seconds
agent_profiles:
  solver:
    executor: acp
    model: …
    api_key: ${ZHIPU_API_KEY}
    options:
      entry: pi
    extensions:
      - plugin: acp
      - plugin: local
```

`environment_options` 给盒子；locator 在 preflight 解析，密钥不进 digest。

## 所有权

| 字段 | 消费者 |
| --- | --- |
| `parameters` | `ctx.params` |
| `limits.*` | Runtime 硬顶 |
| `evaluation/` | evaluate 相位 |
| `environment/` | 盒子配方 |
| `data/` | Agent 可见 seed |
| `profiles.yaml` | 选盒子 / executor / entry |

实现：`src/ageval/config/`（`dataset.py`、`profiles.py`、`load_and_lock.py`、`validate.py`、`digest.py`）。
