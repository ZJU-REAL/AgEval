# Evaluation

writer 必须先停。然后 upload `evaluation/`，再在**同一盒子**里 `host.exec` 跑 `evaluator.py`。禁止 host 进程 `import evaluator` 当 docker/e2b/ssh 的打分路径。

实现：`src/ageval/evaluation/package_evaluator.py` + `box_runner.py` + `bind.py`。相位代码：`src/ageval/attempt/phases/evaluate.py`。

```text
run 结束 → mark_writers_stopped
         → harvest 缺的 publishable：从盒内 /attempt/workspace/<basename>
           download 到 evidence/task-artifacts（已有则跳过）
evaluate
  before_evaluate
  upload artifacts（题包 publish 的 + harvest 补上的）
  upload evaluation/          # gold 此刻才在盒内（引擎代码，不挂链槽，也不是 evaluation SPI）
  evaluation_runtime.evaluate # 独占槽赢家；默认盒内 evaluator.py via host.exec
  bind_evaluation             # Result.status 只在这里写入；赢家返回 raw，不得 bind
  after_evaluate              # 可注 metrics，改 status → RuntimeError
```

PASS 只经 `bind_evaluation` 进入 Result。`RunTerminal.completed`、轨迹完整、ACP 正常结束，都不是 PASS。缺轨迹不得发明 PASS。

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
