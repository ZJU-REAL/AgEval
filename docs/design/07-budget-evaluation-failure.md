# 07 — Budget、Evaluation 与失败语义

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | **本文件与同目录其它 design 文档共同构成设计权威**（自包含；不依赖 vault 总文档） |
| 摘要 | 硬顶与软限、Evaluator barrier、扁平结果、失败分类。 |

---

## 13. Budget 与限制

### 13.1. 硬顶与软限

硬顶由 Runtime/Provider fail closed 强制，任何 Harness 代码都不能提高；软限属于 task workflow，用于实验与停止策略，但仍从同一份 `bora.yaml` 进入 locked config。

| 类型 | 配置位置 | 执行者 | MVP 示例 |
| --- | --- | --- | --- |
| 硬顶 | `limits` | Provider/Runtime/Capability | wall time、memory、process、Agent invocation 总量、Environment action 总量 |
| 软限 | `parameters.agents` | Harness `AgentSession` | 单 Agent max turns |
| 软限 | `parameters.tools` | Harness `CallLimit` | 单 Tool max calls |
| 软限 | `parameters.workflow` | Harness 普通代码/helper | follow-up 次数、fan-out 并发 |
| Campaign 边界 | Campaign plan | Campaign Coordinator | Trial/Attempt/concurrency |

token/cost 只有在 Provider 支持调用前 reserve 时才能成为硬顶；否则只能作为 usage observation，不应把事后统计描述成执行前保证。

### 13.2. 进程内限制的适用范围

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

### 13.3. 旁路防护

Harness guard 只约束经过 Tool callable 的路径。Agent 能直接访问同一个 endpoint 时，Provider 必须关闭旁路：

- 不向 Agent 投影数据库 credential；
- network 只允许受控 proxy 或 sidecar；
- Agent workspace 不包含 private service implementation；
- mutating endpoint 绑定受限 user/group 或 scoped socket；
- shell capability 不包含 host control。

## 14. Evaluation 与结果语义

### 14.1. Evaluator 是 task truth owner

BORA 统一 evaluator 的运行和结果 binding，不统一评分算法。Evaluator 可以检查：

- writer stop 后固定的 declared Artifact；
- 按需 materialize 的 Environment getter/snapshot；
- hidden tests；
- gold labels；
- task-local rubric；
- trajectory 或 communication metrics。

### 14.2. 扁平结果

公共结果只要求 `status`、`score`、`metrics`，可选 `error.phase` / `error.kind`、`cleanup_warning` 与 logs 指针。Runtime 可以内部保存阶段 evidence，但 CLI、网站和聚合器不依赖完整结果树。

Tool denial、预算耗尽、Evaluator 低分、Evaluator crash 和 cleanup failure 仍是不同事实：基础设施错误通过 `status/error` 表达，cleanup 失败通过 warning 表达，不能覆盖有效 score。

### 14.3. Evaluator barrier

```text
Harness returns
  → close Harness capabilities
  → stop Agent/Tool/process writers
  → materialize allowlisted inputs
  → run evaluator
  → validate raw output
  → bind Result + cleanup
```

Runtime 可以在 materialize 内部执行 Artifact digest/只读副本、clean evaluator runtime 或 Environment freeze/getter；只有对应 input strategy 声明时才启用，不把九个内部动作变成每个 task 的公共仪式。

## 15. 失败语义

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
