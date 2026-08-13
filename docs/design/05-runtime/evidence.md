# Runtime — Attempt evidence 与 Agent 轨迹落盘

| 字段 | 值 |
| --- | --- |
| 父索引 | [05-runtime/README.md](README.md) |

---

## 产品要求

BORA 的一次成功或失败 Attempt，必须在 filesystem evidence 根下留下可机器读取的 **Agent 执行轨迹**，用途包括：

1. **观察 / 复盘：** 人读一次 run 里 Agent 说了什么、调用了什么、在哪一步失败；  
2. **轨迹训练 / 离线分析：** 导出 per-invocation 事件与归一化 turn，作为 SFT / preference / offline RL 等数据源；  
3. **后端对比：** 同一 Harness 换 executor/entry 时，比较 latency、usage、事件形态（不比较 business score 时仍可对比轨迹）。

这是 **Runtime / Agent Service 的义务**，不得要求 Harness 自己 `open()` 写训练文件。Harness 经 `ctx.events` 追加的业务事件是**补充**，不能替代 Agent Service 的 invocation 落盘。

## 与「JSONL transport」的区分

| 概念 | 是否默认 | 含义 |
| --- | --- | --- |
| **Evidence JSONL 文件** | **是** | Attempt 目录下的落盘轨迹格式 |
| **Capability JSONL/stdio transport** | 否 | 未来把 Capability 跨进程序列化；见 design/01，非本设计默认 |

## 最小目录契约（logical layout）

路径名可在实现中微调；**语义与所有权**固定：

**Portable locators（#70）：** 密封进 `result.json` / `summary.json` / campaign / trajectory export 的
`logs`、`evidence_root`、`evidence_path`、`evidence_volume` **不得**写 host 绝对路径
（`/Users/…`、`/var/folders/…` 等）。规范值为相对 Database 根的 `.bora/runs/<run_id>`。
`harness.json` 不密封 temp hold 绝对路径（`artifact_hold` 仅布尔；`published` 用 basename / 相对 run）。

```text
.bora/runs/<run-or-attempt-id>/
├── summary.json                 # 扁平 Result 投影 + portable evidence_root / logs
├── lock.json / TaskLocked 摘要  # 无 secret 的锁定引用
├── agent/
│   ├── events.jsonl             # Attempt 级 agent 边界事件索引（可选但推荐）
│   └── invocations/
│       └── <nnnn>-<invocation-id>/
│           ├── metadata.json    # profile、executor kind、entry、model、timing、status
│           ├── request.json     # 归一化 messages / schema / tool specs 摘要（已 redact）
│           ├── events.jsonl     # 后端 stream/event 的 append-only 记录（一行一事件；可含流式片）
│           ├── trajectory.jsonl # **turn 级**训练/导出轨迹（见下文；ACP 默认写出）
│           ├── final-response.json  # 归一化 content / structured_output / usage
│           └── stderr.txt       # 可选；进程型 executor
├── effects.jsonl                # Runtime 边界 effect 决策摘要（tool/env/process 等，若有）
├── evaluation/                  # evaluator raw + binding inputs refs
├── harness/                     # HarnessTerminal 等（可选）
├── cleanup.json                 # cleanup outcome / warning
└── l1-work/                     # L1 host sandbox（workspace / package_view）；见下文
```

### L1 host residual（`l1-work/`）

L1 prepare 把 host work root 放在 **同一 run 目录**下：`.bora/runs/<run_id>/l1-work/`
（workspace、filtered package_view、hold 等）。这是 Attempt **运行期** mount 源，
**不是** Hub / Viewer 的 tab 投影面。

| 策略 | 行为 |
| --- | --- |
| **默认** | Attempt cleanup（含已有 Docker cleanup 的失败路径）后 **删除** `l1-work/`，只保留 Hub-facing 证据 |
| **`--keep-workspace`** | 保留 `l1-work/` 供本地调试；**不**要求 Hub / CI 开启 |
| **Upload pack** | `build_attempt_archive` **排除** `l1-work/**`（即使 residual 仍在磁盘），Registry blob 只含 curated evidence |

Hub Attempt tabs 与本地 `bora view` 仍只解析 Trajectory / Agent / Verifier / Artifacts / Lock / Runtime 等既有相对路径；不新增 Workspace tab。

## 每条 Agent invocation 最小字段

| 文件 / 字段 | 要求 |
| --- | --- |
| `metadata.json` | `invocation_id`、Attempt id、`profile_id`、executor kind、entry（若 acp）、model、started/finished、status、latency |
| `request.json` | 送入后端的归一化 messages（可截断策略在实现契约中冻结）；**禁止**写入 host credential / raw token 值（env locator 名可记） |
| `events.jsonl` | 后端 stream/event 的 append-only 记录；Adapter 可归一化 `type` 字段，但不得丢弃导致无法复盘的关键 turn |
| `trajectory.jsonl` | **Turn 级**训练友好轨迹；**不是** token/chunk 流；**不**决定 PASS |
| `final-response.json` | `content`、可选 `structured_output`、`usage`、session handle 摘要 |
| redaction | secret、Authorization、cookie、DSN password 等不得进入任何轨迹文件 |

## 三层轨迹契约

轨迹分三层，所有权不得混：

| 层 | 所有者 | 形状 | 落盘 / 内存 |
| --- | --- | --- | --- |
| A. vendor raw | 各 adapter / 插件 | 任意 | `backend_raw/*`（观测；不进 Viewer 合成） |
| B. 中立事件流 | **Core schema**；adapter 只做映射 | `bora.trajectory.event/1` | `AgentResult.events` → invocation `events.jsonl` |
| C. turn steps | **Core evidence writer**（不在 `adapters/acp/`） | `trajectory.jsonl` | Viewer / Hub / 训练导出 |

```text
plugin / first-party executor
  → map vendor-native → bora.trajectory.event/1
Core evidence writer
  → fold events → trajectory.jsonl
ACP / nooa / …
  → 各自拥有映射；禁止伪装成另一种协议
```

**禁止：** 非 ACP 插件把 `AgentResult.events` 写成 ACP `session_update` / `tool_call` 再喂给 Core。ACP 是层 B 的一个生产者，不是 schema 权威。插件不得直接写层 C 行（合并规则集中在 Core）。

### `bora.trajectory.event/1`（层 B）

公共信封：`schema`、`seq`、可选 `session_id`、`source`（生产者 id：`acp` / `nooa` / 插件 id）、`kind`。

| `kind` | 字段 | 是否折进层 C |
| --- | --- | --- |
| `text` | `channel: thought\|assistant`，`text` | 是 |
| `tool` | `phase: start\|update`，`tool_call_id`，可选 `title` / `function_name` / `tool_kind` / `status` / `args` / `content` / `raw_output` | 是（Core 按 `tool_call_id` 合并） |
| `permission` | `outcome` / `option_id` / `policy` | 是 |
| `opaque` | 任意 `payload` | **否**（只留 `events.jsonl`） |

无 `schema: bora.trajectory.event/1` 的行不参与层 C 折叠。

## `trajectory.jsonl`（turn 级，训练默认）

**单位：** 一次 BORA `invoke` = **一个 turn unit**，写在该 invocation 目录下。

**与流式 chunk 的关系：**

| 层 | 谁产出 | 是否进 `trajectory.jsonl` |
| --- | --- | --- |
| 后端 token / 片级流 | adapter 内存拼接；可选 vendor raw | **否**（中立 `kind: text` 才进层 B） |
| Turn 全文 | Core 从层 B 合并后写出 | **是** |
| 同一 BORA session 多轮 `invoke` | 多个 `invocations/000n-…/` | 每轮一个目录；可共享同一 `session_id` |

**推荐行类型（JSONL，一行一对象）：**

1. `type=turn` · `role=user` · `content=<完整 prompt>` · `turn_index` · 可选 `session_id` · `source`（生产者）
2. `type=turn` · `role=assistant` · `part=thought` · `content=<合并后的 thought>`（有则写）
3. **`type=tool_call`** · action 侧（有则写；见下）
4. **`type=observation`** · 该 call 的环境回传 / tool result（有则写；与 call 成对）
5. `type=turn` · `role=assistant` · `content=<合并后的最终 assistant 文本>`
6. `type=permission_decision` · batch auto-approve 等（有则写；evidence 决策摘要）
7. `type=terminal` · `ok` / `error` · `structured` / `usage` / `stop_reason` / executor 元数据摘要

行序建议：user → thought →（按首次出现顺序的 tool_call + observation 对）→ assistant 终稿 → permission → terminal。  
无 tool 的 invoke **不写** 3–4。

`source` 是机制/插件 id，**不是**恒为 `acp`。会话字段名是 `session_id`，不是 `acp_session_id`。

### `tool_call` / `observation`（Core 从层 B 折叠）

数据源是 `AgentResult.events` 中的 `bora.trajectory.event/1`（`kind: tool`），**不是** ACP wire，也不是 vendor stdout scrape。ACP adapter 把 `session/update` 映到层 B；其它插件映自己的 native dump。

| 层 B | 轨迹行 | 语义 |
| --- | --- | --- |
| `kind: tool` · `phase: start` | `type=tool_call` | **Action**：模型/agent 发起的工具调用 |
| `kind: tool` · `phase: update` | 合并进同一 `tool_call_id` 的终态；结果写入 `type=observation` | **Observation** ≈ tool result |

**`tool_call` 推荐字段（尽力；缺省可省略）：**

| 字段 | 含义 |
| --- | --- |
| `tool_call_id` | 同 id 多次 update **合并** |
| `title` | 人读标题 |
| `function_name` | adapter 推断的逻辑名 |
| `kind` | tool kind（`read` / `edit` / `execute` / …） |
| `status` | 合并后的终态（`pending` / `in_progress` / `completed` / `failed`） |
| `args` | 调用参数（若有；须 redact） |
| `turn_index` / `session_id` / `source` | 与 turn 行一致；`source` = 生产者 |

**`observation` 推荐字段：**

| 字段 | 含义 |
| --- | --- |
| `tool_call_id` | 对齐对应 action |
| `status` | 该 call 终态 |
| `content` | 可读摘要 |
| `raw_output` | 结构化回传（若有；须 redact） |
| `turn_index` / `session_id` / `source` | 同上 |

**合并规则：** 同一 `tool_call_id` 累积 `title` / `function_name` / `tool_kind` / `status` / `args` / `content` / `raw_output`；seal 发一条 `tool_call` + 可选 `observation`。  
**有 call 无 result：** 仍写 `tool_call`；observation 仅在存在 content / raw_output / 终态 completed|failed 时写出。  
**禁止**只落盘 call 而系统性丢弃已有 result。

**Redaction：** `args` / `content` / `raw_output` 与既有轨迹 redact 同一路径（pattern + sentinels）；禁止 host secret / token 进入 `trajectory.jsonl`。

**Reader fail-open：** 未知 `type` 跳过或原样展示；既有 `turn` / `terminal` 行保持可读。Viewer 与导出工具不得因新行类型硬失败。

**非目标（本机制；导出后置）：** ATIF 一等文件、OpenAI messages JSONL 导出、`--load-trajectory` / session seed、用轨迹充当 PASS。

**多轮会话：** `turn_index` 为 Attempt 内 invoke 序号（1-based）；跨 turn 的 ACP `session_id` 可相同。合并训练样本时以 **invocation / turn_index** 为边界，不要把整个 `session_id` 当成单 turn。

**非目标：** 用 `trajectory.jsonl` 替代 evaluator；要求 harness 自己写训练文件；把 ACP skills 目录类 `AvailableCommandsUpdate` 灌进训练轨迹（应过滤）。训练导出流水线细节可链 Issues（如导出工具演进），不在 design 写进度。

## 所有权与非目标

| 谁 | 写什么 |
| --- | --- |
| **Core evidence writer** | 从层 B 折叠 `trajectory.jsonl`（唯一层 C 作者） |
| Executor Adapter / 插件 | vendor raw → `bora.trajectory.event/1`；`backend_raw/` 保持 native |
| Agent Service | 调用 Core writer；`trajectory_*` 扩展 fail-open |
| Capability / Runtime effect gate | `effects.jsonl` 中授权/拒绝决策摘要 |
| Evaluation Core | evaluator raw + Result binding |
| Harness `ctx.events` | 可选业务侧事件（不得成为唯一轨迹源） |
| Evaluator | 可读 allowlisted 输入；**默认不**把完整 agent 轨迹当作 score 必要条件 |

**非目标（本机制）：** 用轨迹文件替代 evaluator PASS；全局跨 Run 搜索 dashboard；实时 Web UI；保证任意第三方 CLI 的私有日志格式 100% 无损（Adapter 必须至少产出归一化 `final-response` + 尽力层 B 事件；Core 再写层 C）。用 ACP 协议当插件中间格式。保留 `acp_session_id` 或强制 `source: "acp"` 的兼容读。
