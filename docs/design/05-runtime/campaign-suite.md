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
- **补跑**：`--resume-suite` **默认**跳过**真实跑完**的 `(task_id, attempt_index)`（PASS / FAIL / **ERROR** 一律算 finished），**追加**缺失 index 后重算 metrics；suite **cancel 占位**（未真正执行）在 resume 时会**重跑**（避免永久压低 pass@k / pass^k），并清除 `cancel.requested`。
- **点名换槽**：`--resume-suite --task T --replace-slot`（Always-k 再加 `--attempt-index i`，默认 `i=0`）只重跑**被点名**的 finished 槽。无 `--replace-slot` 时行为与上一条相同。这是操作者写路径，**不是** Harbor 式自动重试。
- **进度 / 取消**：suite `progress.json`；`bora status|cancel <suite_run_id>`（可选 `--database`；id 默认为 8 hex）。
- **阶段耗时**：Attempt `phase_timing`（prepare / run / evaluate / cleanup），服务进度与 Viewer/Hub Timing 条；不替代 PASS。

Summary / suite-run 布局见 [02-task-package-and-config.md](../02-task-package-and-config.md)（Database Registry 与 Suite 轴）。

## 点名换槽（finished slot replace）

操作者可以把**已结束** suite 上的一格换成新 Attempt，**同一** `suite_run_id`，旧 Attempt 只进审计链。

| 项 | 契约 |
| --- | --- |
| 谁可被换 | **任意** status（ERROR / FAIL / PASS）。操作者点名 task（Always-k 再点 `attempt_index`）。不自动重试。 |
| Attempt 身份 | **永远**新 `run_id`。不改旧 `result.json` / score / identity，不删旧 evidence 树。 |
| Suite 身份 | **同一** `suite_run_id`。 |
| 槽键 | `k=1`：一 task 一条链。Always-k：一格 `(task_id, attempt_index)`，k 分母仍是 k。 |
| 历史形状 | 每评分槽 **现行指针 + `previous[]`**（oldest → newest superseded）。v1 **没有**整份 `summary.json` 快照版本。 |
| 公布指标 | 只按**现行指针**重算 `pass_rate` / `mean_score` / `pass@k` / `pass^k`。`previous[]` 不进分母。 |
| 绑定 | 新 Attempt 必须与该 suite 同一 Database / 同一 `config_fingerprint` / job overlay 家族。换 profile 当补丁 → 拒绝。 |
| 拒绝 | suite 仍在跑（`progress.json` 未结束）或存在 `cancel.requested`；缺本地新 `run_id`；`run_id` 属于别的 suite；指纹不一致。 |
| 写路径 | 本地 CLI + Registry API。Hub / Viewer **只读**链（默认现行）。 |
| 与 `--replace` | `bora results upload-suite --replace` 仍是**整行 blob 覆盖、不留历史**。换槽**不得**静默走那条路径。 |

落盘（`bora.suite.summary/1`）：

- `attempts[]` 只含**现行**样本（每槽一行）。被换下的现行行收成瘦快照推进该槽 `previous[]`（`run_id` / `status` / `score` / `attempt_index` / `started_at` / `replaced_at`）；旧行若已有 `previous[]` 则前缀保留。`started_at` 是该 Attempt 自己的开始时间；`replaced_at` 只记录指针何时挪走。
- `task_refs[]` 的 `run_id` / `attempt_run_ids` 只列现行；另带该 task 各槽的 `previous[]`（无历史则省略）。
- 任一槽被换过：`amended: true`（审计；**不**取消 Public Leaderboard 资格）。完备性仍按现行指针：PASS / FAIL / ERROR 都算「有 result」。

Registry：PATCH 一条已存在的 suite 行，接收**已上传**的新 Attempt，改该槽现行指针，旧 blob **不删**。`GET` 返回现行 + `previous[]`。所有权与今日 suite 上传 / `--replace` 相同。

## 多 Attempt / 重试（设计契约）

- 重试、矩阵单元、Always-k 样本、取消后的再跑、**点名换槽** → **新 Attempt identity**；
- 不静默改写旧 Attempt 的 score 或 identity；
- 换槽只改 suite 现行指针与指标，不改 PASS 权威（仍是独立 evaluator）；
- multi-attempt 编排细节（并行度、k、resume、replace-slot）属 Application / CLI job 参数面；稳定不变量见 [lifecycle.md](lifecycle.md)。
