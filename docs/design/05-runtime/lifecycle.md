# Lifecycle

一次公开 `ageval run --task` 铸造：Run → Trial（lock digest）→ Attempt。重跑是新 Attempt，不改写旧身份。一次 Attempt 只 `new_run` 一次。

## 外层状态

```text
created
  → locking          # load_and_lock
  → preflight        # host.preflight；缺钥在此失败
  → environment      # start + seed + setup
  → run              # run.py + ACP
  → evaluate         # 停写 + gold + bind
  → record
  → cleanup          # finally，任何失败路径都进
  → terminal         # PASS | FAIL | ERROR
```

实现：`application/run.py` 铸造 identity 与 evidence 根，然后 `attempt.run_attempt`。相位失败记 `phase_failed` 事实；`BaseException`（取消）仍传播；cleanup 总是跑。

## 相位

1. **environment** — `host.start`，upload `data/`，链 `after_environment_ready`（ACP 探测再装；齐了跳过）、`environment_setup`（`setup.sh`，末槽，不是 provision phase）。
2. **run** — 子进程调 `run.py`。Agent invoke 走 parent socket。结束时停 Agent Service 并 `mark_writers_stopped`。
3. **evaluate** — 停 writer 之后 upload `evaluation/`，环境内跑 `evaluator.py`，`bind_evaluation`。
4. **record** — collect/enrich → 引擎写 `trajectory.jsonl`。
5. **cleanup** — `try/finally` 里 `host.stop`。失败记 warning，不改已绑定分数。

没有 provision phase。没有 `run_l0.py` / `run_l1_*.py`。

## 顺序不变量

1. 未 lock 成功不得 start / invoke。
2. Evaluator 不得与可写 Agent/`run.py` writer 并发面对同一评测输入。
3. cleanup 必须可从超时/取消/异常进入。
4. Campaign 只调度格点，不与 `run.py` 内 scheduler 合并。
