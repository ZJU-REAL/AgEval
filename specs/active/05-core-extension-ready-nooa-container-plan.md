# Spec 05 — Core 扩展 Ready：image_contribute 消费 + nooa 容器内执行 + lifecycle 真接线

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-11 |
| Status | **completed** |
| Completed | 2026-08-11 |
| Dependencies | [00](00-extension-registry-default-plan.md), [01](01-acp-default-providers-plan.md), [02](02-nooa-provide-switch-plan.md), [03](03-cli-plugin-lifecycle-plan.md) |
| Decisions | [constitution §0 / §1 / §3 / §7.1 / §7.6 / Recognition≠Ready](../constitution/2026-08-11-extension-api-and-registry.md) |

## 背景（为何重开 · 相对 00–02 的缺口）

00–03 已交付：**注册表、ACP first-party、外置 nooa path install、lock 图、host SPI 级 journeys**。  
下列 **Core 机制** 与 constitution / 产品预期仍不一致（**零容忍**；本 Spec 必关）：

| # | 缺口 | 现状 | 预期 |
| --- | --- | --- | --- |
| 1 | `image_contribute` | hook 只 append 声明；`collect_image_contribute` **无人调用** | Attempt **prepare/bake** 合并声明并驱动镜像 Ready |
| 2 | nooa L1 Ready | **host-in-container**（parent SPI 写挂载）冒充 Ready | nooa **在 Attempt 容器内**执行；`host_fallback_count=0` 且 **不得**用 host SPI 顶 L1 |
| 3 | lifecycle emit | `extension_hooks` 嵌套 loop 时 **skip + unawaited**；错误 fail-open | 固定相位 **真 await**；bake/prepare 相关失败 **fail closed** |
| 4 | Recognition vs Ready | install 后像「全 Ready」 | install = Recognition only；L1 必须 bake 证据 |
| 5 | journeys 终态 | 确定性 package agent + 部分 L0 host | **path install 后** journeys **全部 task** 真 `bora run`；**凡 Agent 路径 nooa 在 Docker 内** |

**不在本 Spec：** Hub SPA / Viewer UI / 商店排序 / 远程运营（Spec 04 已有 API 侧，前端与上线逻辑不动）。

---

## User Story

作为 **本机机制操作者**，我可以：

1. `bora plugin install <path-to-plugins/nooa>` 只扩大 **Recognition**；  
2. profiles 绑 `executor: nooa` + `options.agent`；  
3. `bora run examples/journeys --task <全部四个> --profiles profiles.nooa.yaml`  
   且 **所有 Agent invoke 的 nooa 在 Docker Attempt（或等价容器）内执行**；  

从而证明：**Recognition（install）≠ Ready（image_contribute → bake）≠ 绑定（profiles）**，且 Core 扩展链不是空壳 hook。

---

## Acceptance（对抗性 · 分阶段）

### 总硬门槛（Spec 完成唯一标准）

在 **仅 path install 外置 nooa**（无 first-party 默认注册）前提下：

```bash
export BORA_HOME=<tmp>
uv run bora plugin install plugins/nooa
# 对 examples/journeys 四个 task 逐一：
uv run bora run examples/journeys --task <task> \
  --profiles examples/journeys/profiles.nooa.yaml
```

| Task | 要求 |
| --- | --- |
| `terminal-jsonl-agg` | exit 0；可评分；**assurance=l1**；evidence `executor_kind=nooa`；**执行在 Attempt 容器内**（见 A3）；`host_fallback_count=0` |
| `tau2-dialog-min` | exit 0；可评分；evidence 中 Agent 路径 `executor_kind=nooa`；**nooa 在 Docker 内**（见 A3） |
| `multiagent-env-min` | 同上 |
| `env-postgres-min` | exit 0；无 Agent；装 nooa **不破坏** env 路径 |

- [x] **四 task 均真实 `bora run` 达标**（无 `BORA_OFFLINE_AGENT`；禁止用 host-in-container 或 deterministic 借口跳过「容器内」）。  
- [x] **L1 / Docker Agent 路径禁止** parent 直接 `NooaExecutorSPI.invoke` 作为成功路径。

### A. image_contribute 必须被消费（Core）

- [x] **A1** 存在唯一生产入口：L1（及本 Spec 要求的 Docker Agent prepare）在 **build/prepare 前** 调用 `collect_image_contribute`（或等价合并 API），输入为 **已绑定 profile 的 ExtensionGraph 链**。  
- [x] **A2** 合并结果 **驱动** 镜像内容或等价 bake 步骤（Dockerfile 生成/片段合并 / build-arg / 预装 worker 之一，**写进代码与证据**）；禁止只写 JSON 声明不进镜像。  
- [x] **A3** nooa 绑定后，镜像或容器内 **可执行** nooa worker / entry（名称可实现自定，但 evidence 可证明 invoke 落在容器内）。  
- [x] **A4** 未装 nooa / 未绑定 nooa 时，**不**强制 bake nooa；默认 ACP 路径不回归。  
- [x] **A5** bake/prepare 失败 → Attempt **ERROR fail closed**，不得 silent host 成功。

### B. nooa 容器内执行（取代 host-in-container 终态）

- [x] **B1** 删除或降级为 **测试-only / 显式 env 调试** 的 host-in-container 成功路径；默认 L1 **不得**走 parent SPI 顶成功。  
- [x] **B2** L1 `make_target_executor`（或后继）：`executor_kind=nooa` → **docker exec / 容器内进程** 调 SPI 或 worker，workdir = 容器内 Attempt workspace。  
- [x] **B3** evidence：`executor_kind=nooa` 且 `execution_location`（或等价字段）= 容器侧；`host_fallback_count=0`。  
- [x] **B4** journeys 中 **所有带 Agent 的 task**：为满足「Docker 内 nooa」，允许且 **应当** 将 task `provider.kind` 升为 `docker`（或 Database/job 覆盖），**禁止** 终态验收仍落在纯 host L0 Agent invoke。`env-postgres-min` 可保持无 Agent。

### C. lifecycle 真接线（Core）

- [x] **C1** `before_prepare` / `after_prepare` / run / evaluate / cleanup 在 `bora run` 主路径上 **实际 await**；禁止「有 event loop 就 skip + unawaited coroutine」。  
- [x] **C2** 与镜像/隔离相关的 hook 失败：**fail closed**（至少 prepare/bake）；非关键观测 hook 可记录后继续，但必须 **文档化且可测**，默认不得静默吞掉 prepare 失败。  
- [x] **C3** 单测：嵌套 loop / 同步 `bora run` 两条路径 hook 均被调用（spy 或 counter）。

### D. Recognition ≠ Ready

- [x] **D1** path install 后：`plugin list` / executors 可见 nooa；**未** bake 前 L1 nooa run **不得** PASS（缺 Ready → 明确错误 kind，如 `plugin_not_ready` / `image_contribute_unsatisfied`）。  
- [x] **D2** 文档/注释/Spec 证据写清三句：install ≠ bind ≠ Ready。  
- [x] **D3** （可选但推荐）Config 白名单与 registry Recognition 关系写清：名字可识别 ≠ provide 已装；**不得**未装却 lock 成功。

### E. 失败面

- [x] 未 install + `executor: nooa` → lock/run fail closed（回归 02/03）。  
- [x] 已 install 但 bake 声明无法满足 → run fail closed。  
- [x] 缺 `options.agent` → 稳定错误。  
- [x] install **不**改 profiles。

### F. 回归

- [x] **未装 nooa** 时默认 ACP journeys 主路径（至少 `terminal-jsonl-agg` ACP lock + 既有 L1 行为）不破。  
- [x] `tests/plugins` + 本 Spec 新增 Core 单测绿；ruff/pyright 相关路径绿。

### G. 非目标（禁止塞进本 Spec）

- Hub SPA / Viewer / 上线运营 UI。  
- 远程 `org/id@version` 体验打磨（API 已有则不动）。  
- 真 LLM 质量评测（可用确定性容器内 agent，但 **必须** 在容器内执行）。  
- first-party 复活 `contrib/nooa`。

---

## Scope

- **Included：**  
  - 生产路径消费 `image_contribute`；  
  - nooa 容器内 Ready + L1/Docker executor 接线；  
  - lifecycle emit 真 await + prepare fail closed；  
  - journeys 四 task path-install 后终态 e2e；  
  - 删除/封死 host-in-container 作为 L1 成功路径；  
  - 为 Docker 内 nooa 所需的 package/Dockerfile/worker 最小实现。  
- **Deferred：** Hub UI（非本 Spec）；完整多插件 bake 优化；真 LLM journeys。

---

## 实现思路

### 必读

| 主题 | 链接 |
| --- | --- |
| Recognition ≠ Ready；L1 bake | constitution **§ D. L1 Ready** / §7 |
| 固定扩展点 + multi 链 | constitution §1；[00](00-extension-registry-default-plan.md) |
| nooa 外置、禁止 first-party | [02](02-nooa-provide-switch-plan.md) + constitution |
| path install cache | [03](03-cli-plugin-lifecycle-plan.md) §7.1B |
| L1 prepare / 镜像 | `src/bora/application/run_l1_prepare.py`、`provider_docker`、`docker/attempt` |

### 目标控制流（终态）

```text
bora plugin install plugins/nooa
  → ~/.bora/plugins + index          # Recognition only

bora run … --profiles profiles.nooa.yaml
  → load_and_lock
       ensure_bootstrapped + load_installed_plugins
       resolve executor=nooa → lock.extension_bindings
  → L1 / Docker prepare
       collect_image_contribute(graph)   # 真调用
       merge declares → bake into Attempt image / package image
       失败 → ERROR fail closed
  → start container
  → harness session.invoke
       make_target_executor(nooa) → docker exec | in-container worker
       workdir = /attempt/workspace
       禁止 parent NooaExecutorSPI 成功路径
  → evaluator → PASS/FAIL
```

### nooa 容器内最小 Ready 策略（实现可选其一，Acceptance 只认容器内）

| 策略 | 说明 |
| --- | --- |
| **W1 worker** | 镜像 bake `bora-executor-nooa`（或插件声明的 bake 列表）；parent `docker exec` 调 worker CLI/JSON-RPC |
| **W2 in-image SPI** | bake 插件 Python 到镜像；容器内 Python 调同一 factory（parent 只发 prompt/workdir） |

**禁止终态：** parent 直接 import 任务 `lib.agents` 写 host 挂载并宣称 L1 PASS。

### lifecycle 修复要点

- `extension_hooks._run`：已有 running loop 时用 `asyncio.get_event_loop().create_task` **或** 专用 thread + `asyncio.run`，**禁止**丢弃未 await 的 coroutine。  
- prepare 路径：bake 相关异常向上抛，由 `run_l1` 打 ERROR。

### journeys 调整边界

- 允许改 `examples/journeys/tasks/*/task.yaml` 的 `provider`（升 docker）及 `environment/Dockerfile` **FROM/依赖**，以支撑容器内 nooa。  
- **禁止** 为 nooa 改 harness 业务 `if executor == "nooa"`。  
- 包内 `lib.agents` 可保留确定性逻辑，但须 **在容器内** 被调用。

### 禁止

- bootstrap 默认注册 nooa。  
- host-in-container 作为 L1 验收成功路径。  
- 只改 Spec 勾选不改代码。  
- 用 unit 代替四 journeys `bora run`。  
- 动 Hub/Viewer 上线逻辑。

---

## Phases（阶段验收 · 每 Phase 可独立 fail）

### Phase 0 — 基线与封口 host 假 Ready

**目标：** 标明现状；禁止继续扩 host-in-container 为验收。  
**验收：**

- [x] 文档/Spec（本文件）列出缺口表；  
- [x] 代码注释或测试标明：L1 `kind=nooa` + parent SPI = **非**生产 Ready（或直接删成功路径，Phase 2 完成前可暂 `NotImplemented`/ERROR）。

### Phase 1 — lifecycle 真 await + prepare fail closed

**目标：** Core lifecycle 不再空转。  
**验收：**

- [x] C1–C3 满足；  
- [x] 同步 `bora run` 与「已有 loop」场景均无 unawaited 警告（相关路径）；  
- [x] 单测：hook counter ≥1 on prepare。

### Phase 2 — 消费 `image_contribute` 驱动 bake

**目标：** 声明链 → 镜像内容。  
**验收：**

- [x] A1–A5 满足；  
- [x] 绑定 nooa 时 prepare 日志/证据含 contribute 合并结果；  
- [x] 故意破坏 bake 输入 → run ERROR。

### Phase 3 — nooa 容器内 executor

**目标：** Docker 内 invoke。  
**验收：**

- [x] B1–B3 满足；  
- [x] 最小 e2e：`terminal-jsonl-agg` + path install nooa → PASS，evidence 容器内 + `executor_kind=nooa`。

### Phase 4 — journeys 全部 case 终态

**目标：** 总硬门槛。  
**验收：**

- [x] 四 task 表全绿；  
- [x] B4 满足（Agent task 均 Docker 内 nooa）；  
- [x] D1–D2、E、F 满足；  
- [x] Spec 02 中「host-in-container 可过 L1」表述被本 Spec 覆盖废止（02 Evidence 可加 supersede 注记，**不**回滚 02 外置形态）。

### Phase 5 — 工程门禁与关闭

**验收：**

- [x] ruff / pyright / `tests/plugins` + 本 Spec 新增测；  
- [x] Evidence 节填真实命令与 logs 路径；  
- [x] Status → completed **仅当** 总硬门槛全勾。

---

## Evidence（完成后填写 · 禁止空勾）

| 项 | 内容 |
| --- | --- |
| `BORA_HOME` | `/tmp/bora-spec05-e2e-81476` |
| install 命令 | `bora plugin install plugins/nooa` |
| 四 task status/score/logs | **terminal-jsonl-agg** PASS score=1.0 assurance=l1 logs=`examples/journeys/.bora/runs/sha256_7b84b4778b7cc7e75065d1a5b0b5508bbadefe1ef_run_4184809c45dc`；**tau2-dialog-min** PASS score=1.0 l1 logs=`…/sha256_b1ec21283a1ce2e6aa3dcbba97cdde5da273ea14f_run_5d786c996b06`；**multiagent-env-min** PASS score=1.0 l1 logs=`…/sha256_59d6d79828a3d8f61b315ff906115bb3f1b816e17_run_2d54d4129e06`；**env-postgres-min** PASS score=1.0 l0 (no Agent) logs=`…/sha256_d87dc3e1d3f8659ff17a8c4503773626ecb1466c0_run_c9472a0f6301` |
| L1/容器 evidence 字段 | `executor_kind=nooa`；`execution_location=attempt-container`（invoke events + l1.json）；`host_fallback_count=0` |
| bake 证据 | e.g. `bora-pkg:terminal-jsonl-agg-7b84b4778b7c-nooa-d4848dffa705`；`image_contribute.status=baked` + declares `ready_strategy=in-container-worker` |
| 反例 | 未装：`plugin 'nooa' has no provide for slot 'executor'`；unit：bound+empty contribute → `image_contribute_unsatisfied`；not installed → `plugin_not_ready` |
| 单测 | `BORA_HOME=<empty> uv run pytest tests/plugins -q` → 39 passed；`tests/plugins/test_extension_hooks_await.py` / `test_image_contribute_bake.py` / `test_nooa_container_executor.py` |

---

## 与既有 Spec 关系

| Spec | 关系 |
| --- | --- |
| 00 | 补全 lifecycle/prepare **真**接线；不重做 registry |
| 01 | ACP 仍 first-party；本 Spec 不把 ACP 改外置 |
| 02 | **废止**「host-in-container 可作为 L1 终态 Ready」；保留外置 + path install |
| 03 | 继续 path install 为 Recognition 唯一本 Spec 装入方式 |
| 04 | **不改** Hub/Viewer 上线；远程装包非本 Spec 门槛 |

---

## 完成定义（DoD）

1. 上表 Acceptance **总硬门槛** 全勾且 Evidence 非空。  
2. Core 缺口 1–5 **关闭**。  
3. 无 first-party nooa；无 L1 host SPI 成功路径。  
4. 未碰 Hub/Viewer 上线逻辑。
