# Spec 02 — nooa：外置插件切换（非 first-party）

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-11 |
| Status | **completed** |
| Completed | 2026-08-11 |
| Dependencies | [00](00-extension-registry-default-plan.md), [01](01-acp-default-providers-plan.md), [03](03-cli-plugin-lifecycle-plan.md)（path install） |
| Decisions | [constitution §B.6 / §4 / §7.2–7.6](../constitution/2026-08-11-extension-api-and-registry.md) |

## 现状 vs 目标（必读 · 纠正偏差）

| | **当前错误状态（2026-08-11 实现偏差）** | **正确目标（产品 / 本 Spec）** |
| --- | --- | --- |
| nooa 形态 | 主仓 `src/bora/plugins/contrib/nooa/` + **bootstrap 默认 `register_nooa_contrib`** | **外置 `bora.plugin/1` 包**；`bora plugin install`（path）后进入 `~/.bora/plugins` / index → `load_installed_plugins` |
| 与 ACP 对比 | 误仿 ACP first-party | **仅 ACP** 可为 first-party contrib（主路径）；**nooa 是生态插件实例**，不得默认内置进主仓业务 |
| 已有证据 | unit dual-graph；host `nooa-host-min` PASS（走内置 SPI） | **不算**本 Spec 终态验收 |
| 终态验收 | — | **外置 nooa 装入后**，用 nooa binding 跑通 **`examples/journeys` 全部 task** 的真实 `bora run`（见 Acceptance） |

**禁止继续：** 把 nooa 当作默认 first-party 勾「Spec 02 completed」。  
**允许过渡：** 实现期可暂留 SPI 源码于插件包内（非 `contrib/`）；主仓 bootstrap **不得**默认注册 nooa。

### 偏差原因（审计）

实现 00–02 时为在 Spec 03 install 就绪前让 `executor: nooa` 可 resolve，擅自将 nooa 做成 bootstrap first-party。**非产品决策。** 纠正：拆出外置包 + 删默认注册。

---

## User Story

作为 **Dataset / 机制作者**，我可以：

1. `bora plugin install <path-to-nooa-plugin>` 把 **外置 nooa 包** 装进本机 cache（**不**改 profiles）；  
2. 在 profiles 写 `executor: nooa` + `options.agent`（槽选用 nooa 的 provide）；  
3. **不改 harness.py** 跑 journeys（及同 Database 多 task）；  

从而证明：**Recognition（装插件）≠ 绑定（profiles）≠ Ready（L1 若需要 bake）**，且与 acp binding 可并存。

---

## Acceptance（终态 · 对抗性）

### A. 形态与装入

- [x] **nooa 不是 first-party：** `bootstrap_registry` **默认**不 `register_nooa_contrib`；主仓 **无** `plugins/contrib/nooa` 业务实现（或仅 re-export 文档指针，无默认注册）。  
- [x] **外置包存在：** 仓库内有可 path-install 的 `bora.plugin/1` 包（建议 `plugins/nooa/` 或 `examples/plugins/nooa/`，含 `plugin.yaml` + provide(executor) entry）。  
- [x] **Success install：** `BORA_HOME=<tmp> bora plugin install <nooa-pkg>` → index 含 `plugin_id=nooa`；`bora executors` / discover 可见 `nooa`。  
- [x] **未 install：** profiles `executor: nooa` → lock/run **fail closed**（plugin not found），不得静默回落 acp。

### B. 绑定与 lock

- [x] profiles `executor: nooa` + `options.agent` → lock `extension_bindings.<profile>.executor.plugin == nooa`，`source` 含 `profile_executor_field`。  
- [x] 同 profiles 可混用 `solver=nooa` 与 `user=acp`（若 task 有多 profile）；session graph 分 profile。  
- [x] harness **无** `if executor == "nooa"` 业务分支。

### C. 终态真 e2e（**本 Spec 硬门槛**）

在 **已 path-install 外置 nooa**、且 journeys profiles（或专用 `--profiles`）将 **需要 Agent 的 profile** 绑到 nooa 的前提下：

| Task | 要求 |
| --- | --- |
| `terminal-jsonl-agg` | `bora run examples/journeys --task terminal-jsonl-agg` → 可完成且可评分（status 非因 nooa 装配 ERROR；目标 PASS 或记录可解释 FAIL） |
| `tau2-dialog-min` | 同上（多 ACP 角色改为 nooa 或 nooa+acp 混用时，至少 **所有 invoke 槽来自已装插件 / 合法 provide**） |
| `multiagent-env-min` | 同上 |
| `env-postgres-min` | **无 Agent**：仍须 `bora run` 通过（回归 env；证明装 nooa 不破坏无 Agent 路径） |

- [x] **四条 journeys 均真实 `bora run` 跑通**（exit 0 且结果 JSON 可解释；有 Agent 的 task 须 evidence 中 `executor_kind`/plugin 为 **nooa** 或混绑时 per-profile 正确）。  
- [x] **L1：** `terminal-jsonl-agg` 若仍走 Docker，nooa 必须 Ready（image_contribute / worker / 或文档化的 host-in-container 策略）；**禁止** host_fallback 伪装成功。

### D. 失败面

- [x] 缺 `options.agent` → 稳定可测错误。  
- [x] 未装插件 + `executor: nooa` → fail closed。  
- [x] install **不**改 `profiles.yaml` / `bora.yaml` / `task.yaml`。

### E. 回归

- [x] **未装 nooa** 时：journeys **默认 ACP** 路径仍可按既有证据跑通（Spec 01 主路径）。  
- [x] Spec 03 path install / Spec 00 registry 单测不红。

### F. 工程与文档

- [x] ruff / 相关 pytest；journeys 专用 profiles 或 README 写清 nooa 命令。  
- [x] 文档明确：**ACP = first-party；nooa = 外置插件**。

---

## Scope

- **Included：** 外置 nooa 包；path install；bootstrap 去掉默认 nooa；profiles 切换；journeys 四 task 真 e2e；与 acp 混绑；fail closed。  
- **Deferred：** Hub 远程 publish nooa（[04](04-hub-plugin-package-kind-plan.md) 可复用）；完整 L1 JSONL worker 若 journeys 已能以其它 Ready 策略跑通可记 follow-up，但 **不得**用 first-party 冒充外置验收。

---

## 实现思路

### 必读

| 主题 | 链接 |
| --- | --- |
| 插件 vs `lib/agents` | [constitution §B.6](../constitution/2026-08-11-extension-api-and-registry.md) |
| profiles 短绑定 | [§7.3](../constitution/2026-08-11-extension-api-and-registry.md) |
| install 落盘 | [§7.5](../constitution/2026-08-11-extension-api-and-registry.md) + [Spec 03](03-cli-plugin-lifecycle-plan.md) |
| ACP 仅 first-party | [Spec 01](01-acp-default-providers-plan.md) / constitution §4 |

### 推荐控制流

```text
1. 新建 plugins/nooa/（或 examples/plugins/nooa/）
   plugin.yaml  format: bora.plugin/1
   slots.provide executor → factory 返回 ExecutorSPI
2. 将现 contrib/nooa 实现 **迁入** 插件包 src；删除或掏空 plugins/contrib/nooa
3. bootstrap: include_nooa=False 默认；仅 load_installed_plugins
4. 提供 examples/journeys/profiles.nooa.yaml（或文档化 --set）
5. BORA_HOME=… plugin install …/nooa
6. bora run examples/journeys --task <each> --profiles profiles.nooa.yaml
```

### 任务侧

- 各 journey 若需 typed Agent：包内 `lib/agents` + `options.agent`（仍属 package）。  
- **禁止** 为切 nooa 改 harness 业务分支。

### 禁止

- bootstrap 默认 first-party nooa。  
- 主仓 `contrib/nooa` 作为产品交付形态。  
- install 自动改 profiles。  
- 用 unit / host-only `nooa-host-min` **代替** journeys 四 task 终态验收。

---

## Phases

- [x] Phase 0：Spec/文档纠正（本文件）；标清错误状态  
- [x] Phase 1：外置 `bora.plugin/1` nooa 包 + 迁出 SPI；bootstrap 默认不注册 nooa  
- [x] Phase 2：path install + lock 图 + 未装 fail closed  
- [x] Phase 3：journeys 四 task 真 e2e（外置 nooa）+ ACP 回归 + Acceptance  

## Evidence（完成后填写）

### install

```bash
export BORA_HOME=/tmp/bora-nooa-e2e-final
uv run bora plugin install plugins/nooa
# → plugin_id=nooa version=0.1.0 digest=sha256:d5ab49b6594197fd495b9ff8efd15a5bd3f4d4438e5299143b1f18516b7316d7
```

未装：`BORA_HOME=<empty> bora lock … --profiles profiles.nooa.yaml` → exit 2  
`extension resolve failed … plugin 'nooa' has no provide for slot 'executor'`。

### lock 片段

`extension_bindings.solver.executor.plugin == "nooa"`，`source == "profile_executor_field"`，`version == "0.1.0"`。

### 四条 journeys（真实 `bora run`，无 `BORA_OFFLINE_AGENT`）

| Task | status | score | assurance | executor_kind | logs |
| --- | --- | --- | --- | --- | --- |
| `terminal-jsonl-agg` | PASS | 1.0 | l1 | nooa | `…/sha256_2c67ab54…_run_7499bf08e5ab` |
| `tau2-dialog-min` | PASS | 1.0 | l0 | nooa | `…/sha256_68fbafff…_run_9892e314fd33` |
| `multiagent-env-min` | PASS | 1.0 | l0 | nooa | `…/sha256_876a41d1…_run_cc86fbfcdf00` |
| `env-postgres-min` | PASS | 1.0 | l0 | (no agent) | `…/sha256_d87dc3e1…_run_68d49a7758a3` |

L1 Ready：`host-in-container`（parent SPI 写 Attempt workspace mount）；`host_fallback_count=0`；官方镜像标签 `bora-attempt:l1` / `bora-pkg:*`。

### bootstrap 默认无 nooa

- 代码：`src/bora/plugins/bootstrap.py` 无 `register_nooa_contrib`；`include_nooa` 已删除。  
- 测试：`tests/plugins/test_acp_nooa_contrib.py::test_bootstrap_default_has_no_nooa`。  
- 主仓 **无** `src/bora/plugins/contrib/nooa/`。

### 单测

`uv run pytest tests/plugins/ -q` → 24 passed。
