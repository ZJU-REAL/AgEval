# Evaluation

writer 必须先停。然后 upload `evaluation/`，再在**同一盒子**里 `host.exec` 跑 `evaluator.py`。禁止 host 进程 `import evaluator` 当 docker/e2b/ssh 的打分路径。

实现：`src/ageval/evaluation/package_evaluator.py` + `box_runner.py` + `bind.py`。相位代码：`src/ageval/attempt/phases/evaluate.py`。

```text
run 结束 → 停 solver writer（run 相位已打开的 session 不得再 invoke）
         → Agent Service 保持（或 reopen）到 evaluate 结束
         → harvest 缺的 publishable：从盒内 /attempt/workspace/<basename>
           download 到 evidence/task-artifacts（已有则跳过）
evaluate
  before_evaluate
  upload artifacts（题包 publish 的 + harvest 补上的）
  upload evaluation/          # gold 此刻才在盒内（引擎代码，不挂链槽，也不是 evaluation SPI）
  evaluation_runtime.evaluate # 独占槽赢家；默认盒内 evaluator.py via host.exec
                              # 可选：evaluator.py 调 Agent.session(<role>).invoke
  bind_evaluation             # Result.status 只在这里写入；赢家返回 raw，不得 bind
  after_evaluate              # 可注 metrics，改 status → RuntimeError
```

PASS 只经 `bind_evaluation` 进入 Result。`RunTerminal.completed`、轨迹完整、ACP 正常结束、judge 输出、`evaluation/observation.jsonl` 是否写全，都不是 PASS。缺轨迹不得发明 PASS。

`evaluation_runtime` 默认仍是盒内 `evaluator.py`。缺省路径：evaluator **不**调 `Agent.session` → 无 `evaluation/observation.jsonl`，Verifier 仍是 `result.json` + `evaluation/` 文件树。这是 opt-in，不是新槽、不是新 profile 文件。

## 可选：evaluate 相位 SDK invoke（LLM-as-judge）

同一份 job `profiles.yaml` 多一行 `agent_profiles.<id>`（例：`judge`），task 角色表列入同一 id。gold **已经** upload 之后，`evaluator.py` 可以 `Agent.session("judge").invoke(...)`（可多次）。提示词归题包。`invoke` kwargs 仍不得改 `profile_id` / executor。

这些 invoke 走 **同一** Parent Agent Service 与该 profile 自己的 executor 赢家（ACP、openai-http、…）。同一 Attempt 上 solver 与 judge **可以** 选不同机制（solver `acp`、judge `openai-http`）。`environment` 仍是 Attempt 级一份。

约束：

- gold 进盒之后，**solver（run 相位已用过的 profile）不得再 invoke**。
- evaluate 相位的 invoke scratch 不得进 `agent/invocations/`，以免 Agent 页 / 根 `trajectory.jsonl` 吞掉。布局字符串只在 `src/ageval/evidence/`。
- 密封行写入 `evaluation/observation.jsonl`（层 C，与 Agent 轨迹同一行形）。**省略 `user` 行**（judge 提示常含 hidden reference）。不是 bind 的输入，不拷进 `result.json` / `metrics` / `summary.extra` / `evaluation/evaluator_raw.json`。
- `evaluator.py` 仍返回 `{status, score, metrics}`；`bind_evaluation` 只读这份。

低分是有效 FAIL。cleanup 失败只 warning。evaluator 缺产物应 FAIL，不要把 KeyError 变成引擎崩溃。

## gold：时间切开（默认隔离）

```text
environment / run     /attempt/evaluation  不存在
evaluate 开头         host.upload(evaluation_src, /attempt/evaluation)
                      然后 exec evaluator.py
```

- Agent / `run.py` / `environment_setup` **禁止**看到 `evaluation/`（不 upload、不 mount、不 COPY 进 Agent 用镜像层）。
- 这是 Harbor 同档的 **时间切开**，**不是** `path_views`。不要只靠 YAML 删字段。
- evidence 可记 gold 在 evaluate 才 materialize。
- 另开 Host 打分 **不是默认**。

`path_views` 是额外能力（当前仅 docker 报 yes）：同时多角色不同盘（mount+UID）。不要用它表示「晚上传 gold」。

失败归属总表见 [ARCHITECTURE.md](../../../ARCHITECTURE.md) § Failure and Privacy Boundary。
