# Runtime — Environment Manager

| 字段 | 值 |
| --- | --- |
| 父索引 | [05-runtime/README.md](README.md) |
| 章节锚点 | 原 design §8.5 |

---

## 契约

Environment Manager 按资源类型选择 Adapter。所有 Environment 至少实现：

- resource instance 与 Attempt 绑定；
- prepare、allowlisted action、teardown；
- action allowlist；
- Environment action 总上限；
- teardown 后资源是否可以复用。

reset、observe、freeze、snapshot 和 evaluator getter 是按资源与评测策略启用的扩展。只有 evaluator 需要环境终态时，Runtime 才在 writer stop 后调用相应策略；artifact-only task 不承担这些动作。

## Harness 包装为业务 Tool

Harness 可以把 Environment client 包装成任意业务 Tool：

```python
database = ctx.environment.require("database-attempt")


async def inspect_lock_contention() -> dict[str, object]:
    return await database.action(
        "inspect_lock_contention",
        {},
    )
```

Tool name 和业务 policy 留在 Harness；Environment 只检查当前 capability 是否允许调用这个 action，以及资源是否处于可写或可读阶段。

## 边界

| Environment 做 | Environment 不做 |
| --- | --- |
| namespace、secret projection、action ceiling | 解释 Benchmark 业务 action catalog 的语义 |
| prepare / teardown lifecycle | 持有 host credential 写入 package |
| 按需 freeze / getter | 替代 evaluator 形成 PASS |

Adapter 按**资源类型或执行机制**命名；禁止按 Benchmark / task / domain 名分支。
