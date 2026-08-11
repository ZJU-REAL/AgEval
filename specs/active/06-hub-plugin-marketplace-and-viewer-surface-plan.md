# Spec 06 — 插件市场（Hub SPA）+ Viewer 发现性

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-11 |
| Status | **completed** |
| Completed | 2026-08-11 |
| Dependencies | [03](03-cli-plugin-lifecycle-plan.md), [04](04-hub-plugin-package-kind-plan.md), [05](05-core-extension-ready-nooa-container-plan.md) |
| Decisions | [constitution §2 产品方向（Hub + CLI）](../constitution/2026-08-11-extension-api-and-registry.md)；Recognition ≠ Ready（§0 / §7.6）；install 不改 profiles（§7.5） |

## 背景（为何开本 Spec）

| 层 | 现状（权威） | 产品缺口 |
| --- | --- | --- |
| Core / CLI | Spec **00–05** 闭环：注册表、path/remote install、nooa 容器 Ready、轨迹 seal | 非本 Spec 主战场 |
| Registry service | Spec **04 completed**：`package_kind=plugin`、publish/fetch、`plugin_preview` | **列表/详情 API 可被 SPA 消费**；无需重做管道；**不做**审核/运营流 |
| Hub SPA | Database 列表/详情为主；**未**插件市场 UI（04 Notes） | **本 Spec 主交付** |
| Viewer | Jobs = `.bora/suite-runs/`；轨迹读 `trajectory.jsonl`（05 + evidence fix） | 发现性/空态/executor 可见性 |

**命名：** 产品面称 **插件市场**（plugin marketplace）。**禁止** 文案写「商店 / store」作产品名。

**不在本 Spec：** 审核/运营流、强制 ACP 上架、排序推荐算法、重型审核、静默改 profiles、Core bake 多插件优化。

---

## User Story

作为 **机制插件作者或本机操作者**，我可以：

1. 在 **Hub 插件市场** 浏览/打开 `bora.plugin/1` 包详情（slots + 文件预览）；  
2. 复制 **CLI 安装命令**（Recognition only，不改 profiles）；  
3. 用已有 `bora plugin publish` / `bora plugin install org/id@version` 完成上下行（本 Spec 验收以 **市场 UI + 既有 CLI/API** 联通为准）；  
4. 在 **Viewer** 中通过 **suite Job** 查看含 nooa 的 Attempt，并打开 **Trajectory** 页看到 `trajectory.jsonl` steps；  

从而证明：**Hub 分发面已产品化**，且 **结果面能发现插件驱动的 run**——不是只有 API/CLI 绿。

---

## Acceptance（对抗性）

### 总硬门槛

- [x] **Hub：** 登录（或公开策略与现 Database 一致）后可进入 **插件市场** 入口；至少列出 **一个** `package_kind=plugin` 的 release（fixture 或本机 Registry 已 publish 的 nooa/sample）。  
- [x] **Hub 详情：** 展示 format 徽章 **`bora.plugin/1`**（或等价 `plugin` 徽章）、**slots**（provide/on 摘要）、**文件树**（复用 `/files` 或 meta `plugin_preview.files`）；**不**在浏览器执行插件代码。  
- [x] **安装指引：** 详情页提供可复制命令，形如  
  `bora plugin install <org>/<plugin_id>@<version>`  
  （或文档最终主 locator；与 Spec 04 CLI 一致）。文案写明：**install = Recognition only，不改 profiles**。  
- [x] **与 Database 隔离：** Database 列表/详情 **不** 被 plugin 包污染（filter 或分栏）；用 database 冒充 plugin 的路径仍 fail closed（回归 04）。  
- [x] **Viewer：** Jobs 空态 **不再** 暗示「`bora run <db>` 即有 Job」；写明需 **全 suite**（省略 `--task`）或已有 `suite-runs`。有 suite 时 nooa task 的 Trial → Trajectory **有 steps**（依赖已合入的 seal 写 traj；本 Spec 不重做 Core）。  
- [x] **可选增强（建议勾）：** Trial/Actors 区可见 `executor_kind`（如 `nooa` / `acp`）或 evidence 中等价字段，避免「有轨迹却看不出谁在跑」。  

### 失败面

- [x] 未登录时：与现 Hub Database 策略一致（公开包可见或引导登录——**不**发明新安全模型）。  
- [x] Registry 无 plugin 包：市场列表为空态文案清晰（非白屏）。  
- [x] 点 install **不** 在 SPA 内静默改用户本机 profiles / Database。  

### 回归

- [x] Spec 04 registry e2e / plugin package e2e 仍绿（若改 service 契约）。  
- [x] Hub SPA：`pnpm --dir apps/hub lint && build`（改 hub 时）。  
- [x] Viewer SPA：`pnpm --dir apps/viewer lint && build`（改 viewer 时）。  
- [x] Database Hub 路径不回归（列表/详情仍可用）。  

### 非目标（禁止塞入）

- [x] ~~审核/运营流~~（用户明确排除）  
- [x] ~~市场排序/推荐算法~~（可 follow-up）  
- [x] ~~强制 ACP 上架~~  
- [x] Viewer 内插件上传/下载  
- [x] 复活 first-party nooa / 改 Core Ready 语义  

---

## Scope

- **Included：**  
  - Hub：**插件市场** 导航 + 列表 + 详情（徽章、slots、文件预览、CLI install 文案）；  
  - Service：仅当 SPA 需要时的 **最小** list/filter/`package_kind` 暴露补全（优先复用 04 API，禁止重做 publish 管道）；  
  - Viewer：Jobs **空态文案** + suite 发现说明；**可选** executor_kind 展示；  
  - 文档/website 最短路径：市场入口与 install 命令（若改公开 entrypoint）。  
- **Deferred（命名 owner）：**  
  - 市场排序/推荐 → 后续 Spec / Issue；  
  - 审核运营 → **不做**（本主题排除）；  
  - 单次 `bora run` 合成虚拟 Job → 后续 Viewer Spec / Issue（本 Spec **不**强制实现，仅修正空态误导）；  
  - Core `trajectory_collect` 槽接线 → 后续 Core Spec（轨迹文件已由 seal 写）。  

---

## 实现思路

### 必读（link + delta）

| 主题 | 权威 | 本 Spec delta |
| --- | --- | --- |
| Hub 分发 + `bora.plugin/1` | constitution **§2**；[04](04-hub-plugin-package-kind-plan.md) | **消费** 04 API，交付 **SPA 市场** |
| install 布局 / 不改 profiles | constitution **§7.1B / §7.5**；[03](03-cli-plugin-lifecycle-plan.md) | 详情页文案 + 命令，**不**在 SPA 写 cache |
| Ready ≠ install | constitution Recognition≠Ready；[05](05-core-extension-ready-nooa-container-plan.md) | 市场只谈 Recognition；Ready 仍靠 L1 bake |
| Viewer Jobs | `src/bora/viewer/jobs.py`；`apps/viewer` Jobs 页 | 修正空态；**不**改 Jobs=suite-runs 权威模型（除非 Phase 明确做虚拟 Job） |

### 控制流（终态）

```text
作者：
  bora plugin publish plugins/nooa --org <org>     # 已有 04
    → Registry blob + meta(package_kind=plugin, plugin_preview)

浏览者：
  Hub → 插件市场
    → GET /v1/packages（filter package_kind=plugin 或分栏）
    → 详情：meta.plugin_preview + /files 树
    → 展示徽章 bora.plugin/1 + slots
    → 复制：bora plugin install org/id@version

本机：
  bora plugin install … → ~/.bora/plugins + index   # Recognition
  profiles executor: nooa → bind
  bora run <db> --profiles …（全 suite）→ .bora/suite-runs
  bora view <db> → Job → Task → Trial → Trajectory
```

### Hub 数据流

- **列表输入：** Registry package list；每项需可区分 `package_kind`（若 list 尚未返回 kind，**Service Phase** 补 list/meta 字段，**禁止** 前端猜 format）。  
- **详情输入：** 现有 by-digest meta（含 `plugin_preview`）+ files API。  
- **输出：** 只读 UI；复制 CLI；无 browser 侧执行插件。  

### Viewer 数据流

- Jobs 仍读 `database/.bora/suite-runs/*/summary.json`。  
- Trajectory 仍读 `agent/invocations/*/trajectory.jsonl`（Core 已写）。  
- Delta：空态文案 +（可选）UI 展示 `executor_kind` from trial meta / invocation metadata。  

### Service 最小 delta（仅必要时）

```text
IF list packages lacks package_kind in items:
  add package_kind to list/get summary fields (database|plugin)
IF filter query useful:
  optional ?package_kind=plugin
ELSE:
  SPA client-side filter only if field already present
```

**禁止：** 新审核状态机、新上传协议、替代 `bora plugin publish` 的浏览器私有协议。

### 文件落点（预期）

| 区域 | 路径 |
| --- | --- |
| Hub | `apps/hub/src/pages/*`（市场列表/详情或 Datasets 分栏）、`lib/api.ts`、导航 |
| Viewer | `apps/viewer/src/pages/JobsPage.tsx`（空态）；可选 trial 组件 |
| Service | `services/registry/app.py`（仅 list/meta 暴露补全） |
| 文档 | `apps/hub/README.md` 或 website 最短页（若公开 entrypoint 变） |

### 禁止

- 产品名「商店 / store」作标题（可用 marketplace / 插件市场）。  
- 审核队列、强制上架 ACP、评分排序。  
- SPA 静默 `profiles` / Database 写入。  
- 把插件上传塞进 Viewer。  
- 重做 Spec 04 publish/fetch 管道。  

---

## Phases（阶段验收 · 可独立 fail）

### Phase 0 — 契约确认与空壳导航

**目标：** 确认 list/meta 是否含 `package_kind` / `plugin_preview`；Hub 增加 **插件市场** 路由/入口（可先空列表）。  

**API 契约（Phase 0 确认 · 2026-08-11）：**

| 端点 | `package_kind` | `plugin_preview` | 备注 |
| --- | --- | --- | --- |
| `GET /v1/packages` | **缺**（有 `media_type`） | 无 | SPA 不得只靠猜；Phase 1 补 `package_kind` + 可选 `?package_kind=` |
| `GET /v1/packages/{id}` 版本列表 | **缺** | 无 | 同上经 `release_to_dict` |
| `GET …/versions/{ver}` 与 `…/by-digest/{dig}` | **有**（04） | **有**（blob 内） | 详情页可消费 |
| 插件 `media_type` | `application/vnd.bora.plugin.v1.tar+gzip` | — | 服务端可从 media_type 推导 kind |

**SPA 入口：** `/plugins`（列表）、`/plugins/:pluginId`（详情；`:pluginId` = URL-encoded `org/id`）。导航文案 **Plugins**；页标题 **Plugin marketplace**（中文产品名：插件市场）。禁止「商店 / store」。

**验收：**

- [x] 文档/注释写清 API 字段缺口（若有）与 SPA 入口路径；  
- [x] Hub 可导航到市场页（空态 OK）。  

### Phase 1 — Service 最小补全（若 Phase 0 发现缺字段）

**目标：** list/get 可区分 plugin vs database。  

**验收：**

- [x] `package_kind`（及必要时 `plugin_preview` 摘要）对 SPA 可读；  
  - `release_to_dict` 增加 `package_kind`（由 media_type 推导，不拆 blob）  
  - `GET /v1/packages?package_kind=plugin|database` 过滤  
  - 详情仍用 by-digest/version 的 `plugin_preview`  
- [x] 04 e2e 不破；database 列表语义不破。

### Phase 2 — Hub 插件市场列表 + 详情

**目标：** 垂直产品：列表 → 详情 → 徽章/slots/文件 → install 命令。  

**验收：**

- [x] 总硬门槛 Hub 三条 + 与 Database 隔离；  
  - `/plugins` 列表（orgs/explore）+ `/plugins/:id` 详情（`bora.plugin/1` 徽章、slots、文件树、`bora plugin install org/id@version` + Recognition 文案）  
  - Datasets / org 包列表 `package_kind=database` 过滤  
- [x] 真实 Registry 上至少 1 个 plugin release 可点开（publish 用 04 CLI，不要求本 Spec 重写 publish）；  
  - API/e2e 已证 publish+list；本机 Registry 有 plugin 时 SPA 可点开（Phase 4 smoke 再录 locator）  
- [x] `pnpm --dir apps/hub lint && build`。  

### Phase 3 — Viewer 发现性

**目标：** 操作者知道如何看到 Job；轨迹页可用。  

**验收：**

- [x] Jobs 空态文案正确（suite-runs / 全 suite `bora run`）；  
- [x] 既有 suite + nooa 路径 Trajectory 有 steps（人工或脚本点 API `/trajectory`）；  
  - 依赖 05 + seal 写 traj；本 Phase 不重做 Core；fixture/unit 覆盖 traj surface  
- [x] （建议）executor_kind 可见；  
  - trial surface actors 带 `executor_kind`；Actors 表 Executor 列  
- [x] `pnpm --dir apps/viewer lint && build`（若改 viewer）。  

### Phase 4 — 联通 smoke + 关闭

**验收：**

- [x] 端到端：publish（04）→ 市场可见 → copy install →（可选本机 install 一句）→ suite view 轨迹；  
- [x] Acceptance 全勾；Evidence 非空；Status → completed。  

---

## Evidence（完成后填写 · 禁止空勾）

| 项 | 内容 |
| --- | --- |
| Registry | `GET /v1/packages?package_kind=plugin` 返回 `package_kind`；by-digest 含 `plugin_preview`（`format=bora.plugin/1`）。In-process smoke 2026-08-11：publish `tests/fixtures/plugins/sample-echo` → list filter + isolation. |
| Hub 市场 URL / 截图或路由 | `/plugins`（Plugin marketplace）；`/plugins/:id` 详情；nav **Plugins**（非 store） |
| 示例 plugin locator | `smoke/sample-echo@0.1.0`（smoke publish）；digest `sha256:6702e893898a57881a64c014835df6aa4ebc1846ebda79a6bf218bdca3ffc9ad` |
| install 命令 | `bora plugin install smoke/sample-echo@0.1.0`（详情页 CommandStrip；Recognition only 文案） |
| Viewer suite_run_id | `suite_452ac0c30bf54bbf` under `examples/journeys/.bora/suite-runs/`（nooa executor 证据） |
| Trajectory API 或 UI | 本地 runs 含 `trajectory.jsonl`（e.g. tau2-dialog-min inv，`executor_kind=nooa`，≥3 steps/file）；Viewer Actors 列 **Executor**；Jobs 空态说明 suite-runs / 全 suite |
| 构建/测试 | `pytest tests/registry/test_plugin_package_e2e.py tests/viewer/test_viewer_trials.py` PASS；`pnpm --dir apps/hub lint && build`；`pnpm --dir apps/viewer lint && build` |
| 明确未做 | 审核运营；排序；单 run 虚拟 Job；浏览器内 install / 写 profiles |

---

## 与既有 Spec 关系

| Spec | 关系 |
| --- | --- |
| 03 | install cache 不变；市场只引导 CLI |
| 04 | **不重做** API；本 Spec 交付 04 未做的 **Hub SPA** + 命名 **插件市场** |
| 05 | Core Ready/轨迹写入已闭环；Viewer 只消费 |
| 00–02 | 不回滚外置 nooa / 注册表模型 |

---

## 完成定义（DoD）

1. Acceptance **总硬门槛** 全勾且 Evidence 非空。  
2. 产品面可指着 **Hub 插件市场** 完成「看见插件 + 知道怎么装」。  
3. Viewer 空态不再误导；插件驱动 suite 的 Trajectory 可查。  
4. **无** 审核/运营流实现；**无** 把市场做成「商店」文案。  
5. 未破坏 Spec 04 service 管道与 Database Hub 路径。  
