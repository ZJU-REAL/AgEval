# 07 — Budget、Evaluation 与失败语义

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含；不依赖 vault 总文档） |
| 摘要 | 硬顶与软限、Evaluator barrier、扁平结果、失败分类。 |

---

## Budget 与限制

### 硬顶与软限

硬顶由 Runtime/Provider fail closed 强制，任何 Harness 代码都不能提高；软限属于 task workflow，用于实验与停止策略，但仍从同一份 `bora.yaml` 进入 locked config。

| 类型 | 配置位置 | 执行者 | MVP 示例 |
| --- | --- | --- | --- |
| 硬顶 | `limits` | Provider/Runtime/Capability | wall time、memory、process、Agent invocation 总量、Environment action 总量 |
| 评测沙箱 | `evaluation` | Evaluation Core / L1 clean-eval | `network`（isolated 新容器：`none`\|`bridge`，省略 ≡ `none`）、`tmpfs_mb`（isolated-eval `/tmp`，默认 32 MiB）、`reuse_attempt`（省略 ≡ `false`） |
| 软限 | `parameters.agents` | Harness `AgentSession` | 单 Agent max turns |
| 软限 | `parameters.tools` | Harness `CallLimit` | 单 Tool max calls |
| 软限 | `parameters.workflow` | Harness 普通代码/helper | follow-up 次数、fan-out 并发 |
| Campaign 边界 | Campaign plan | Campaign Coordinator | Trial/Attempt/concurrency |

`evaluation.tmpfs_mb` 只约束 **L1 isolated-eval** 容器的 `/tmp` tmpfs，与 Attempt / Agent 的 64 MiB `/tmp` 无关。它和 `evaluation.network` 同属 isolated 评测运行时，**不要**写成 `limits.eval_tmpfs_*`：`limits` 是 Attempt / Agent / Environment 硬顶，混进去会把两个独立事实绑在同一套「不可 `--set`」契约上。省略则保持 32 MiB fail-closed 默认；非法或非正整数在 lock 失败，不静默放大。

`evaluation.network` 只约束 **新起的** isolated 评测容器（`none | bridge`，省略 ≡ `none`）。`evaluation.reuse_attempt: true` 时评测在 Attempt 容器内跑，网络沿用已有 `provider.network`，**不**重连 live 容器；`placement` / `tmpfs_mb` 也不改写 Attempt rootfs。省略两字段保持今日 isolated、离线 eval。

token/cost 只有在 Provider 支持调用前 reserve 时才能成为硬顶；否则只能作为 usage observation，不应把事后统计描述成执行前保证。

### 进程内限制的适用范围

`CallLimit` 适用于：

- 单个 Harness Attempt；
- 串行 Tool loop；
- 受控 `asyncio` 并发；
- 多个 Tool 共享同一个显式 guard object。

以下情况出现后，才考虑 durable authority：

- 多个进程竞争最后一个额度；
- Harness 崩溃后继续运行；
- 后台 reopen；
- 多个 Attempt 共享额度；
- 额度本身对应外部不可逆资源。

### 旁路防护

Harness guard 只约束经过 Tool callable 的路径。Agent 能直接访问同一个 endpoint 时，Provider 必须关闭旁路：

- 不向 Agent 投影数据库 credential；
- network 只允许受控 proxy 或 sidecar；
- Agent workspace 不包含 private service implementation；
- mutating endpoint 绑定受限 user/group 或 scoped socket；
- shell capability 不包含 host control。

## Evaluation 与结果语义

### Evaluator 是 task truth owner

BORA 统一 evaluator 的运行和结果 binding，不统一评分算法。Evaluator 可以检查：

- writer stop 后固定的 declared Artifact；
- 按需 materialize 的 Environment getter/snapshot；
- hidden tests；
- gold labels；
- task-local rubric；
- trajectory 或 communication metrics。

### 扁平结果与轨迹 evidence

公共**扁平结果**只要求 `status`、`score`、`metrics`，可选 `error.phase` / `error.kind`、`cleanup_warning` 与 **`logs` 指针**。CLI、网站和聚合器**不**依赖完整内部阶段树来判定 pass/fail。

`logs` **必须**解析到本 Attempt 的 evidence 根（见 [05-runtime/evidence.md](05-runtime/evidence.md)）。evidence 树中的 **Agent invocation 轨迹（JSONL 等）是产品必选交付物**，用于观察与轨迹训练；它与 score **正交**：

| 事实 | 权威 |
| --- | --- |
| PASS / score | 独立 Evaluator |
| Agent 说了什么 / 后端事件 / usage | Agent Service 落盘轨迹 |
| 基础设施 error.phase | Runtime |
| cleanup 失败 | `cleanup_warning`，不覆盖 score |

Tool denial、预算耗尽、Evaluator 低分、Evaluator crash 和 cleanup failure 仍是不同事实：基础设施错误通过 `status/error` 表达，cleanup 失败通过 warning 表达，不能覆盖有效 score。**缺少轨迹落盘是 Runtime 产品缺口，不是 evaluator fail。**

### Evaluator barrier

```text
Harness returns
  → close Harness capabilities
  → stop Agent/Tool/process writers
  → materialize allowlisted inputs
  → run evaluator
  → validate raw output
  → bind Result + cleanup
```

Runtime 可以在 materialize 内部执行 Artifact digest/只读副本、clean evaluator runtime 或 Environment freeze/getter；只有对应 input strategy 声明时才启用，不把九个内部动作变成每个 task 的公共仪式。L1 默认仍是新起 isolated 评测容器：只读根文件系统，可写面是 `/tmp` tmpfs；容量读 `evaluation.tmpfs_mb`（省略 32 MiB）。snapshot 大于默认值时由 **task 声明更大的评测沙箱**，而不是抬高全局默认或改 Agent workspace `/tmp`。`evaluation.reuse_attempt: true` 时跳过新容器，在 writer 已停的 Attempt 容器内执行同一份 `evaluator.py`；hidden / gold 仍只在 barrier 之后 materialize，评测进程不得见 `/creds`。

## 失败语义

| Failure | 发生位置 | 结果 |
| --- | --- | --- |
| `bora.yaml` 格式错误 | Config load | 不创建 Attempt |
| 参数引用或 capability 不兼容 | Config validation | 不创建 Attempt |
| Provider/resource unavailable | Prepare | 不启动 Harness，清理已创建资源 |
| Harness import/entrypoint failure | Harness start | Runtime infrastructure failure |
| Agent capability denied | Agent boundary | typed error，Harness 决定是否终止 |
| Tool local policy denied | Harness | local Observation 或 Harness error |
| Environment action denied | Environment boundary | 外部状态保持不变 |
| Harness timeout/cancel | Provider | 停止 writers，保留 Runtime facts |
| declared Artifact 缺失或 writer 未停 | Evaluation input | Evaluator 不启动 |
| Evaluator 返回低分 | Evaluation | valid Benchmark result |
| Evaluator crash/malformed output | Evaluation | evaluation infrastructure failure |
| Teardown failure | Cleanup | 保留已有结果，资源禁止不安全复用 |

Harness 可以将 task-local failure 转成 Observation、retry 或 terminal reason。它不能把 infrastructure failure 伪装成有效低分，也不能发布最终 evaluator verdict。
