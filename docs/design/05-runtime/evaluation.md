# Runtime — Evaluation（Workspace / Artifact / Barrier / Result）

| 字段 | 值 |
| --- | --- |
| 父索引 | [05-runtime/README.md](README.md) |

---

## Workspace 与 Artifact Owner

Workspace 处理“进程能看到哪些路径”，Artifact Owner 处理“哪些 declared output 可以跨边界”。Package 作者只声明 logical name、producer、path 和 media type，并通过 `ctx.artifacts.publish_*` 提交；Runtime 内部负责 path 校验、digest、只读副本和 evaluator materialization，不把 Materialized/Sealed 状态提升为用户类型。

同一 Harness 进程中的 Python object 不需要 Artifact。相同 workspace 中可以传相对路径。缺失 declared output 或 writer 未停止时，Evaluator 不启动。

### WorkspaceView（设计契约）

Provider 按 lock 中的 `provider.workspace.views` 投影 path view（read/write 列表）。actor-specific 或 invocation-specific WorkspaceView 由 Provider 在 prepare 时建立。物理可见性靠 mount / PathGrant / UID/GID，**不是**配置里删字段。

若某细粒度 view 策略不在稳定设计内，标 **非目标** 或由 Issue 跟踪；design 正文不写「目前未实现」状态句。

## Evaluator Runner

Evaluator Runner 创建 clean runtime，只 materialize `evaluation.inputs` 允许的内容：

- writer stop 后固定的 declared Artifact；
- 按需 Environment getter 或 snapshot；
- task identity 和必要 metric config；
- evaluator-only hidden material。

Evaluator 看不到 Agent credential、Harness 用过的可变 workspace、Harness memory 或仍在运行的 writer。Harness 的 `completed` 只表示 loop 已停止，不能直接形成 `PASS`。PASS 只来自包 `evaluator.py` 的返回值。

### L1 落点

L1 用 Attempt **同一张包镜像** 新起评测容器：不挂 package、不挂 `/creds`、不挂 docker.sock、根文件系统 `--read-only`、网络 `none`。入口仍是 `evaluator.py` 的 `evaluate()`。

可写面只有 `/tmp` tmpfs。容量读 `evaluation.tmpfs_mb`（省略 32 MiB，#133）。默认 **`noexec`**。

`evaluation.placement`：

| 值 | `/tmp` exec | 默认超时 | 用途 |
| --- | --- | --- | --- |
| `staging`（默认） | 否 | 90s | 解 snapshot / 读 artifact |
| `writable` | 是 | 300s | 在 `/tmp` 拷干净树、apply、跑测 |

`timeout_seconds` 可选，不超过 `limits.wall_time_seconds`。`writable` 注入 `BORA_EVAL_WORKDIR=/tmp/eval-work`。需要更大磁盘时仍声明 `tmpfs_mb`，不要另起字段。

`evaluation_runtime` 插件不得改笼子、不得决定 PASS。

## Result Binder

对外 Result 保持扁平：

```yaml
status: pass | fail | error | timeout | cancelled
score: 1.0
metrics: { task_accuracy: 1.0 }
error: { phase: evaluation, kind: malformed_output, message: "..." } # 可选
cleanup_warning: "..." # 可选
logs: .bora/runs/<run_id>   # portable under Database root (#70); never host abs
# legacy design sketch also accepted by readers: run://<run_id>
```

**`logs` / evidence locator 契约（#70）：**

| 形态 | 示例 | 说明 |
| --- | --- | --- |
| **规范（推荐）** | `.bora/runs/<run_id>` | 相对 Database 根；与 on-disk 布局一致 |
| 可接受 legacy | 历史 host 绝对路径 | 读者经 `extract_run_id` / `resolve_run_dir` 剥离 |
| 设计 sketch | `run://<run_id>` | 可选别名；实现以相对路径为 sealed 默认 |

`evidence_path`、`summary.evidence_root`、`l1.evidence_volume`、campaign 行 locator **同一契约**。Suite `task_refs[].run_id` 仍为目录名。

**扁平 Result 与 evidence 树分工：**

| 产物 | 消费者 | 是否必选 |
| --- | --- | --- |
| 扁平 `Result`（status/score/metrics/error/cleanup_warning/`logs`） | CLI、Campaign 聚合、比较报表 | **必选** |
| Attempt evidence 树（含 Agent 轨迹） | 操作者复盘、失败诊断、轨迹训练导出 | **必选** |
| 完整内部阶段树 / 九步仪式 DTO | package 作者 / 公开聚合 schema | **非必选** |

Runtime **必须**在 evidence store 中保存至少：Harness terminal 摘要、**每次 Agent invocation 的轨迹文件**、evaluator raw output、cleanup outcome。它们**不是** package 作者必学的公开 Result 树，但**是**产品级交付物：`Result.logs` 必须解析到该 Attempt 的 evidence 根。Evaluator score、基础设施错误与 cleanup warning 不互相改写；**轨迹存在与否不得改变 score 语义**。

详见 [evidence.md](evidence.md)。
