# Evaluation

writer 必须先停。然后把 gold 与产物送进 **打分 Host**。`evaluator.py` 是 **parent 子进程**（与 `run.py` 同一形态）：控制面不 `import evaluator`，经进程边界调用。`Agent.session` 走本机 Parent Agent Service unix socket；evaluate 相位的 ACP `attach_stdio` 打打分 Host。禁止把 evaluator 再 `host.exec` 进盒子再让它 `connect()` 一根挂进去的 socket。

打分 Host 缺省就是 run 那只盒子。job `evaluate_host.isolated: true` 时是 **第二只** EnvironmentProvider 实例（同 kind、不同配方、不同 work root），不是新独占槽。

实现：`src/ageval/evaluation/package_evaluator.py` + `src/ageval/runtime/eval_worker.py` + `bind.py`。相位代码：`src/ageval/attempt/phases/evaluate.py`。harvest：`src/ageval/attempt/artifact_harvest.py`。

```text
run 结束 → 停 solver writer（run 相位已打开的 session 不得再 invoke）
         → Agent Service 保持（或 reopen）到 evaluate 结束
         → harvest 一次：file 缺的从盒内 /attempt/workspace/<basename>
           download 到 evidence/task-artifacts；tree 按 exclude 做成不可变快照
evaluate
  before_evaluate
  [isolated] start 第二 Host（题包 evaluate 配方；独立 work root，不绑 Agent 盘）
  upload artifacts
      file → 打分 Host /attempt/artifacts
      tree + evaluation.inputs.target: workspace → 打分 Host /attempt/workspace
  upload evaluation/          # gold 此刻才在打分 Host（引擎代码，不挂链槽）
                              # isolated：Agent 盒始终没有 /attempt/evaluation
  [isolated] 对未在 run 用过的 ACP profile 再跑 after_environment_ready（打分盒）
  evaluation_runtime.evaluate # 独占槽赢家；默认 parent 子进程跑 evaluator.py
                              # 可选：evaluator.py 调 Agent.session(<role>).invoke
                              # invoke 走 parent JSON-RPC；ACP attach_stdio 打打分 Host
  bind_evaluation             # Result.status 只在这里写入；赢家返回 raw，不得 bind
  after_evaluate              # 可注 metrics，改 status → RuntimeError
cleanup（finally）
  stop 打分 Host（若与 run 盒不同）
  stop run 盒
```

PASS 只经 `bind_evaluation` 进入 Result。`RunTerminal.completed`、轨迹完整、ACP 正常结束、judge 输出、`evaluation/observation.jsonl` 是否写全、harvest 快照在不在、第二 Host 起没起，都不是 PASS。缺轨迹不得发明 PASS。

`evaluation_runtime` 默认是 parent 子进程里的 `evaluator.py`（`src/ageval/runtime/eval_worker.py`），与 `run.py` 共用 Agent Service socket。缺省路径：evaluator **不**调 `Agent.session` → 无 `evaluation/observation.jsonl`，Verifier 仍是 `result.json` + 产物文件树。这是 opt-in，不是新槽、不是新 profile 文件。

## 可选：evaluate 相位 SDK invoke（LLM-as-judge）

同一份 job `profiles.yaml` 多一行 `agent_profiles.<id>`（例：`judge`），task 角色表列入同一 id。gold **已经** upload 之后，`evaluator.py` 可以 `Agent.session("judge").invoke(...)`（可多次）。提示词归题包。`invoke` kwargs 仍不得改 `profile_id` / executor。

这些 invoke 走 **同一** Parent Agent Service 与该 profile 自己的 executor 赢家（ACP、openai-http、…）。同一 Attempt 上 solver 与 judge **可以** 选不同机制（solver `acp`、judge `openai-http`）。`environment` 仍是 Attempt 级一份赢家；isolated 时 evaluate 相位把该服务绑到打分 Host，所以 ACP `attach_stdio` 进打分盒，HTTP judge 仍在 parent 出站。不要把 Agent Service unix socket bind-mount 进容器。

约束：

- gold 进盒之后，**solver（run 相位已用过的 profile）不得再 invoke**。
- evaluate 相位的 invoke scratch 不得进 `agent/invocations/`，以免 Agent 页 / 根 `trajectory.jsonl` 吞掉。布局字符串只在 `src/ageval/evidence/`。
- 密封行写入 `evaluation/observation.jsonl`（层 C，与 Agent 轨迹同一行形）。**省略 `user` 行**（judge 提示常含 hidden reference）。不是 bind 的输入，不拷进 `result.json` / `metrics` / `summary.extra` / `evaluation/evaluator_raw.json`。
- `evaluator.py` 仍返回 `{status, score, metrics}`；`bind_evaluation` 只读这份。

低分是有效 FAIL。cleanup 失败只 warning。evaluator 缺产物应 FAIL，不要把 KeyError 变成引擎崩溃。

## gold：时间切开（默认）；isolated 再加空间切开

```text
environment / run     Agent 盒 /attempt/evaluation  不存在
evaluate 开头         打分 Host.upload(evaluation_src, /attempt/evaluation)
                      然后在打分 Host exec evaluator.py
```

- Agent / `run.py` / `environment_setup` **禁止**看到 `evaluation/`（不 upload、不 mount、不 COPY 进 Agent 用镜像层）。
- 缺省打分 Host = run 盒：Harbor 同档的 **时间切开**，**不是** `path_views`。不要只靠 YAML 删字段。
- `evaluate_host.isolated: true`：gold **只**上打分 Host。Agent 盒整段 Attempt 都没有这份树。不要把 Agent 活 workspace bind-mount / symlink 进打分盒（会漏 `target/`、`*.so`、Agent 安装闭包）。
- evidence 可记 gold 在 evaluate 才 materialize。第二 Host 的 start 不是 PASS。
- 省略 `evaluate_host` = 今日同盒。题包即使有 `environment/evaluate.Dockerfile`，没开开关也不 start 第二盒、不认那份配方。

`path_views` 是额外能力（当前仅 docker 报 yes）：同时多角色不同盘（mount+UID）。不要用它表示「晚上传 gold」，也不要用 compose 侧车当顺序打分镜像。

## 产物：file 与 tree

`artifacts.publishable` 缺省仍是单个文件（`kind` 省略 / `file`）。`kind: tree` 把题包声明的工作区树收成 **一次** 不可变快照（writer 停后、evaluate 前，仍走 `harvest_workspace_artifacts`）。可选 `exclude`（目录名与 glob 路径段，例如 `target`、`*.so`、`.git`）。

- harvest **一次**。后面 evaluate 的 upload / rematerialize / 盒内读取都消费这份快照的拷贝，不是 Agent 活目录，也不是三次 export。
- `evaluation.inputs[].target: workspace` 把 tree 铺到打分 Host 的 `/attempt/workspace`。省略 target 的 file 产物仍上 `/attempt/artifacts`。
- docker：tree download 读已有 bind-mount 再按 exclude 拷到 evidence；不要 `docker cp` 一整棵再在 Core 里拆。
- 打分 Host 的 workspace **不是** Agent bind-mount。harvest 之后改 Agent 树，evaluator 看不见。

快照在不在、exclude 清没清，都不是 PASS。

## isolated 打分 Host

job：

```yaml
# profiles.yaml — 省略 evaluate_host = 同盒
evaluate_host:
  isolated: true
```

lock：

- `isolated: true` 必须能在成员题上落到配方：存在 `environment/evaluate.Dockerfile`，或 `evaluation.docker_image`（OCI tag）。两者都无 → lock 失败，不 start。
- 配方文件 **不** 放 `evaluation/`（那是 gold）。
- Current：`environment: docker`。local / 不能再起一盒的 kind + `isolated: true` → lock 失败。
- 未知 `evaluate_host` 键、未知 `artifacts.publishable` 键：一次错误，不映射。

runtime：第二实例由 composition 用同一 docker 赢家工厂构造（不同 `BoxSpec.attempt_root` + evaluate 配方）。`evaluation_runtime` 仍是独占槽默认引擎，parent 子进程跑 `evaluator.py`。isolated 时对 **未在 run 打开过的 ACP profile** 在打分盒上再跑 `after_environment_ready`（不要拿 solver 的 entry 去装打分镜像）。SDK 仍不得拥有 `host.start` / `host.upload`。

失败归属总表见 [ARCHITECTURE.md](../../../ARCHITECTURE.md) § Failure and Privacy Boundary。
