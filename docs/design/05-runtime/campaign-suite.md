# Runtime — Campaign 与 Suite（设计正交）

| 字段 | 值 |
| --- | --- |
| 父索引 | [05-runtime/README.md](README.md) |
| 交叉 | Suite 轴见 [02](../02-task-package-and-config.md) |

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

## Campaign vs Suite vs Always-k

| 轴 | 含义 | 典型入口 |
| --- | --- | --- |
| **Suite / Database 成员轴** | 同一 Database 下按 **task_id** 调度多个成员 | `bora run`（省略 `--task`） |
| **Campaign / matrix 轴** | 同一 task 的 **parameter / profile / binding matrix** | `bora campaign` |
| **Always-k / k-attempt 轴** | 范围内每个 task **固定 k 次独立 Attempt**，为 pass@k / pass^k 攒样本 | `bora run … -k` / `--n-attempts`；可选 `--resume-suite` |

三者**设计正交**：

- Suite 不负责改写 profile 的 experiment matrix；
- Campaign 不合并进 Attempt 内 Harness workflow scheduler；
- Always-k **不是** campaign matrix 字段，也**禁止**写进 `task.yaml` / `config_fingerprint`；
- 并行（`max_concurrent_tasks`）只压缩**总耗时**，不改变 k，也不改变 PASS 判定；
- 三者都消费 Config Core 的 `load_and_lock`，不维护第二份真配置。

### Always-k 与 job 指标（#47）

- **Always-k**：范围内每 task 固定产出 k 个独立 Attempt（并列或链均可；**不许**改旧 Attempt）。
- **pass@k**：无偏估计（Harbor）；**pass^k**：\((c/n)^k\)；suite / dataset 分 = 各 task 指标的 **mean**（样本不够的 task 不进该 k 分母）。
- **补跑**：`--resume-suite` 跳过已完成 `(task_id, attempt_index)`，**追加** Attempt 后重算 metrics。
- **进度 / 取消**：suite `progress.json`；`bora status|cancel suite_…`（可选 `--database`）。
- **阶段耗时**：Attempt `phase_timing`（prepare / run / evaluate / cleanup），服务进度与 Viewer/Hub Timing 条；不替代 PASS。

Summary / suite-run 布局见 [02-task-package-and-config.md](../02-task-package-and-config.md)（Database Registry 与 Suite 轴）。

## 多 Attempt / 重试（设计契约）

- 重试、矩阵单元、Always-k 样本、取消后的再跑 → **新 Attempt identity**；
- 不静默改写旧 Attempt 的 score 或 identity；
- multi-attempt 编排细节（并行度、k、resume）属 Application / CLI job 参数面；稳定不变量见 [lifecycle.md](lifecycle.md)。
