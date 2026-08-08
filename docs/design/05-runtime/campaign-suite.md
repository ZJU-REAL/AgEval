# Runtime — Campaign 与 Suite（设计正交）

| 字段 | 值 |
| --- | --- |
| 父索引 | [05-runtime/README.md](README.md) |
| 章节锚点 | 原 design §8.10；与 [02](../02-task-package-and-config.md) Suite 轴交叉 |

---

## Campaign Coordinator

Campaign 把 experiment matrix 展开成 Trial，每个 Trial 使用一份 resolved `LockedTaskConfig`。Retry 创建新的 Attempt identity，不静默修改 Trial 分母或 Harness 参数。

Campaign 可以覆盖 `parameters` 中允许变化的字段：

```yaml
variants:
  - id: follow-up-1
    parameters:
      workflow:
        max_follow_up_assignments: 1

  - id: follow-up-2
    parameters:
      workflow:
        max_follow_up_assignments: 2
```

Variant 是 Config Core 的显式输入。它不会成为 Task Package 内第二份被 Harness 直接读取的配置。

## Campaign vs Suite

| 轴 | 含义 | 典型入口 |
| --- | --- | --- |
| **Suite / Database 成员轴** | 同一 Database 下按 **task_id** 调度多个成员 | `bora` suite / 批量 task 选择（以 CLI 为准） |
| **Campaign / matrix 轴** | 同一 task 的 **parameter / profile matrix** | `bora campaign` |

二者**设计正交**：

- Suite 不负责改写 profile 的 experiment matrix；
- Campaign 不合并进 Attempt 内 Harness workflow scheduler；
- 两者都消费 Config Core 的 `load_and_lock`，不维护第二份真配置。

Summary / suite-run 布局见 [02-task-package-and-config.md](../02-task-package-and-config.md)（Database Registry 与 Suite 轴）。

## 多 Attempt / 重试（设计契约）

- 重试、矩阵单元、取消后的再跑 → **新 Attempt identity**；
- 不静默改写旧 Attempt 的 score 或 identity；
- multi-attempt 编排细节（并行度、配额）属 Application / Campaign 实现面；稳定不变量见 [lifecycle.md](lifecycle.md)。
