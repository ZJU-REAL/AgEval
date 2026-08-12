# 决策：扩展点 + 注册表（写法 B）与交付切分

## Metadata

| Field | Value |
| --- | --- |
| Decision date | 2026-08-11 |
| Branch / 开发基线 | **`canary`**（后续本主题分支均从 canary 拉出并合回 canary） |
| Related specs | [00](../active/00-extension-registry-default-plan.md) · [01](../active/01-acp-default-providers-plan.md) · [02](../active/02-nooa-provide-switch-plan.md) · [03](../active/03-cli-plugin-lifecycle-plan.md) · [04](../active/04-hub-plugin-package-kind-plan.md) |

本文件是本主题 **自包含** 产品/机制决策（含背景）。Active Spec 只写故事与验收，不重复长文。

---

## Background

### B.1 问题从哪来

BORA 要支持 **可插拔的 Agent 后端 / 机制扩展**（不止 coding-agent ACP），同时保持：

- Package **`harness.py` 机制无关**（只 `bora_sdk` 的 `session.invoke` 等）；
- Core 拥有生命周期、隔离、投影、额度、evaluator barrier、证据权威形状；
- 可复盘：某次 Job 在 **何种扩展组合** 下跑出。

已有切片（事实基线，非本决策发明）：

| 现状 | 含义 |
| --- | --- |
| `executor: acp` + `options.entry` | coding-agent **主路径**（builtin） |
| entry point 组 `bora.agent_executors` | 可装 kind（如实验性 nooa），偏 **pip/开发态** |
| nooa 示例 | L1 JSONL worker + task 侧 `lib/agents` + Dockerfile vendor bake |
| Database / results | 已走 Hub/Registry；**机制插件未与之同构** |

痛点：

1. **分发分裂**：Dataset 上 Hub，机制插件靠 pip/vendor，作者路径不一致。  
2. **认识 vs 就绪混淆**：host 装了包 ≠ L1 镜像能跑（Recognition ≠ Ready）。  
3. **可复现不足**：缺少「扩展点 → 实现@digest」进 lock 的一等叙事。  
4. **扩展深度未产品化**：nooa 证明了换 executor 一条路，未定义稳定扩展面与多插件组合律。  
5. **心智噪音**：builtin / entry point / task `lib` / 镜像 bake 职责缠在一起。

### B.2 目标用户故事（交付要对齐的「为什么」）

| 角色 | 想做什么 | 可观察结果 |
| --- | --- | --- |
| 操作者 | 默认装 BORA 就能跑 ACP 主路径 | 不装任何外置「全量 ACP 插件包」也能 `bora run` |
| Dataset 作者 | 换机制后端时 **不改 harness** | 同一 `harness.py`，只改绑定/安装的扩展贡献 |
| 机制作者 | 发一个插件包支持新 executor/环境贡献等 | Hub 上下 + CLI 安装后 kind 可 Recognition |
| 复盘者 | 看懂 Job 在什么插件组合下跑的 | lock / 结果侧有扩展点绑定摘要 |
| 平台 | 多插件共存、可审、可拒 | 注册表 + 优先级/冲突策略，非 import 序玄学 |

**非目标（本主题不靠插件偷偷做）：** 默认让任意插件静默改 PASS、旁路隔离门闩、自提 hard ceiling、主仓塞第三方业务 Agent 类。

### B.3 讨论中收敛过的错误路径（避免回潮）

| 曾考虑 / 易混 | 为何放下 |
| --- | --- |
| pip install 到 site-packages = 产品装插件 | 与 L1 Ready 脱节；与 Hub 分发不一致 |
| CLI 往 cwd 落盘当 pip 副作用 | 惊吓、不可复现 |
| 主仓塞 nooa skill / 业务 | 违反「主仓无第三方插件业务」 |
| **全量 ACP 打成外置插件包** 再测槽位 | 主路径过险；与「默认 fallback」相反 |
| **继承整条 Attempt/Runtime 类** 当插件主模型 | 难多插件同点、优先级、lock；且易被误解成 harness 写插件类 |
| 巨型主仓业务树冒充扩展模型（与薄 `plugins/` 内核无关） | 扩展模型是注册表+扩展点，不是把第三方业务塞进主仓 |

**写法 A（子类）澄清：** 若采用继承，正确形态是 composition root 注入子类实例，base 管线内 `self.hook()` **多态**调到子类——**不是**在 `harness.py` 写 `NooaRuntime()`。即便如此，A 仍不适合作为 **多插件主模型**。

### B.4 为何定写法 B（固定扩展点 + 注册表）

业界同类：pytest hooks + `@hookimpl`、VS Code contributes、CKAN plugin interfaces、多种 agent 的 tool/provider 注册——均为 **宿主固定节点 + 插件登记贡献**。

相对 A 的收益（贴合已定用户故事）：

- **多插件同点**：链上多个 handler + 优先级；  
- **只换一点**：`provide("executor", …)` 不动 before 链；  
- **默认可解释**：默认也是注册上的 builtin 贡献；  
- **可复现**：解析后的图进 lock；  
- **harness 零感知**：装配全在 Runtime / Agent Service。

### B.5 链槽 vs 单赢家（执行语义，易错点）

| 类型 | 串行？ | 默认是否跑 | 例子 |
| --- | --- | --- | --- |
| **链 multi** | 是（`next()`） | 默认常为链上一环，**会跑**（除非短路/卸默认） | `before_agent_invoke`；`image_contribute` 合并声明；`cleanup_actions` |
| **单赢家 provide** | 否 | 仅当未被更高优先替换 | `executor`（Acp **或** Nooa，不是两个都 invoke） |

轨迹常见拆分：`trajectory_collect` 可链合并；`trajectory_seal` / evidence **权威形状** 默认侧，避免每后端一种盘格式。

### B.6 与 package / nooa 的分工（避免「插件 = 任务 Agent」）

| 层 | 职责 |
| --- | --- |
| Harness（package） | 业务时序：`session.invoke`、读 workspace、publish |
| 扩展点贡献（Core 默认 / 插件） | 机制：如何 invoke、镜像声明、轨迹采集片段… |
| Task 程序（如 NOOA `lib/agents.py`） | 框架侧 **typed Agent 类 / schema**——属 package，不是 BORA 主仓，也不是「装了插件就自带每个 task 的 Agent」 |

因此：装 nooa 插件解决 **BORA 怎么调 NOOA runtime**；task 仍可能补 `lib/agents` + `options.agent`。

### B.7 开发基线

- 本主题工作区与后续功能分支以 **`canary` 为基线**：从 canary 开分支、合回 canary。  
- 本 worktree 路径示例：`bora-canary-plugin`（实现细节可变）；**分支名以 canary 族为准**。

---

## Decision

### 0. MVP 实现纪律（本主题强制）

本主题在 **greenfield MVP** 上落地扩展点 + 注册表，**不**承担向后兼容旧装配路径的义务。

| 规则 | 含义 |
| --- | --- |
| **不向后兼容** | 旧 `resolve_executor` 双轨、静默 fallback、TypeError 重试、可选 registry「有则用无则旧」等 **一律不保留** |
| **删除优先于胶水** | 新模型覆盖旧路径时 **直接删除** 旧入口与 shim；禁止「新路径 + 旧路径并存」的临时双写 / 门面转调 / 兼容层 |
| **测试与调用方同步改** | 单测、CLI、composition root **改到新入口**；不为旧签名留死代码 |
| **fail closed** | 缺 provide、冲突、未钉 graph → 显式失败，不回落到 import 序或全局单例 |

**反例（禁止）：** `if graph: use graph else: resolve_executor(...)`；`DefaultExecutor` 内部再调 `agent_registry.resolve_executor` 假装兼容；`try: import plugins except: skip extension_bindings`。

**正例：** Parent Agent Service **只**从 session 钉死的 `extension_graph.providers["executor"]` 取实现；lock **必须**写出 `extension_bindings`；旧 entry-point 解析路径在接线完成后 **删除**。

### 1. 扩展模型：固定扩展点 + 注册表

**采用写法 B，不采用「继承整条 AttemptRuntime 管线」作为插件主模型。**

| 概念 | 含义 |
| --- | --- |
| **扩展点（slot）** | 宿主在 phase / agent 管线的 **固定名字** 上 `emit` / 查询注册表 |
| **注册表** | 收集 handler（链）与 provider（单赢家）；解析优先级与冲突 |
| **默认实现** | 以注册方式挂上的 **内置贡献**，不是神秘硬编码分支 |
| **插件** | 只向声明的扩展点 `on` / `provide`；不改 harness.py |
| **装配** | Composition root / Agent Service 解析注册表；harness 只 `session.invoke` |

单槽 provider 可用 class 实现接口（如 `NooaExecutor`）——这是 **槽内实现方式**，不是继承整机 Runtime。

**登记 API（名称可随实现微调，语义固定）：** `@on(slot, priority=…)` / `provide(slot, impl, priority=…)` —— 登记到扩展点，不是任意 override 私有方法。

**链槽改写语义（终态已定）：** handler 为中间件形态，**允许** 经 `next` 包装改写 prompt / result；不调用 `next` = 短路（须在契约中写明允许的槽与后果）。

**默认 handler 可卸（终态已定）：** 默认可被更高优先 / 显式绑定策略 **替换或卸掉**（文档化 `replace_default` 或等价机制）；卸掉后的行为必须进入 lock 绑定图。

### 2. 产品方向（Hub + CLI + 可复现）

1. 机制插件经 **Hub 上传/下载**；format **`bora.plugin/1`**；包内 **manifest 声明 slots**（on/provide）；可预览完整 package。  
2. 主路径：**Hub + `bora` CLI** → 本地 cache/注册表；pip 非主路径。  
3. **扩展点绑定（实现@版本/digest、优先级结果）进 lock**，Job 可展示。  
4. **冲突规则（终态已定）：** **显式绑定 > 数字优先级**；**平局 fail closed**；禁止 import 序静默覆盖。  
5. **用户绑定声明（终态已定）：** **扩展 profiles**（如 executor/options 及后续扩展字段）；解析后 **lock 展开为完整扩展点图**（lock 为运行真相）。  
6. Package **harness 机制无关**；换绑定仍应能跑；内部差异允许。  
7. 任务特有逻辑可在 package（如 `lib/agents`）；主仓不塞第三方插件业务。  
8. 文档/skill 随插件包；CLI 可物化；用户显式 cp/软链。  
9. **Recognition ≠ Ready**。  
10. nooa 等是生态实例，非架构终点。

### 3. 公开扩展点 = 完备集 L0–L5（终态已定）

**终态：L0–L5 全部作为对外契约公开**（三方可 `on`/`provide`，受冲突规则与审核/安装约束）。  
**L6** 为注册表/lock/Hub 元机制，属平台内核，不是「业务扩展点」清单的一部分。

**Attempt 骨架：** `prepare → run → evaluate → cleanup`。

**公开扩展点地图（id 名可实现期统一命名，分层不可删）：**

- **L0：** attempt/phase 前后钩子（prepare/run/evaluate/cleanup 书挡）  
- **L1：** `image_contribute`、`env_prepare_commands`、`env_inject`、`env_action`、`env_teardown_commands`、…  
- **L2：** `executor`（单赢家）、`before/after_agent_open|invoke|close`（链）、`normalize_agent_result`、…  
- **L3：** 评测邻接（含 `evaluation_input_contribute`、`evaluation_runtime`、`score_postprocess` 等）— **已公开**，实现须把「改评测语义」的绑定 **完整写入 lock**，以便 Job 不可假装与默认评测同轴  
- **L4：** `trajectory_collect`（链）、`trajectory_enrich`、`trajectory_seal`、`evidence_extra`、…  
- **L5：** `cleanup_actions`、`cleanup_report`  

两步法在本决策中的用法：完备地图 = 公开契约；实现按 Spec 00–04 **一口气交付**，不搞「先只开一个槽的上线分期」。

### 4. 默认实现 vs ACP 专有

> 通用 fallback → **默认注册贡献**。  
> **禁止** 全量 ACP 插件包承载 prepare→cleanup 整链。  
> **ACP 专有** 只 `provide`/`on` 独有点：协议 executor、entry/镜像贡献、协议侧 collect。  
> **seal / evidence 默认形状** 由默认贡献提供，但按 §1 **可被合法替换/卸掉**（须进 lock）。

| 验收 | |
| --- | --- |
| 主 | 默认注册下 ACP 主路径仍跑通 |
| 次 | nooa 等只 provide 差异槽可切换 |
| 否 | 先拆默认、只留外置全量 ACP 包 |

### 5. 实现分层（终态方向）

```text
宿主管线（application / agent service）
  → 固定点 emit / 查 Registry.resolve()
  → 链 handler 串行（可改写）或 单 provider.invoke
默认贡献（与 Core 同发）—— 注册为 builtin（可被卸/替）
专有填充（acp first-party / Hub bora.plugin/1）—— on/provide
CLI install → 本地 store → 扩大 Recognition
L1 bake ← image_contribute 合并声明（Ready）
profiles 绑定 → resolve → lock 完整图
```

`src/bora/plugins/` 只放宿主内核（registry/resolve/defaults/contrib）；**不要**把第三方业务实现堆进主仓该包。

### 6. 交付切分（User Story 级；一口气完成，非上线分期）

| Spec | 可验证结果 |
| --- | --- |
| 00 | 注册表 + 默认注册 + 冲突规则 + lock 完整绑定图 |
| 01 | ACP 默认/专有注册；无全量 ACP 包时主路径跑通 |
| 02 | nooa provide 等；harness 不变可切换 |
| 03 | `bora plugin` 安装/列表 → Recognition；docs 物化可选 |
| 04 | Hub `bora.plugin/1` 发布/预览/下载 |

逻辑依赖：00→01→02；03 依赖 00；04 依赖 03。实现上可并行开发，但验收按依赖闭合。

---

## 7. 验收目标证据（终态 · 实现必须对齐）

> 本节是 **可观察验收契约**：文件夹布局、配置形状、install 落盘、resolve 调用链。  
> 路径字符串可微调，但 **职责与数据流不可歪**。实现以本节为验收真相；各 Spec「实现思路」链回本节并补 Spec 特有步骤。

### 7.1 文件夹架构

#### A. Core（`src/bora`）— 宿主扩展面，非插件业务大仓

```text
src/bora/
├── plugins/                   # 宿主插件子系统（注册表/resolve/默认与 first-party 贡献；第三方包不在此）
│   ├── __init__.py
│   ├── slots.py               # L0–L5 公开扩展点 id；标注 multi(链) / provide(单赢家)
│   ├── protocol.py            # SPI：ExecutorProvider、HookHandler(next)、ImageContribute…
│   ├── registry.py            # 注册表：on/provide、priority、按 plugin_id 索引
│   ├── resolve.py             # binding 意图 + 注册表 + 冲突规则 → ExtensionGraph
│   ├── middleware.py          # 链槽串行 next（允许改写 prompt/result）
│   ├── conflict.py            # 显式绑定 > priority；平局 fail closed
│   ├── lock_bind.py           # ExtensionGraph → lock 字段 extension_bindings
│   ├── defaults/              # 默认贡献（builtin 注册，可被卸/替）
│   │   └── …                  # 各槽默认 handler/provider
│   └── contrib/               # first-party 专有（非全量外置 ACP 包）
│       └── acp/               # executor、image/entry、协议侧 trajectory_collect…
├── application/               # lifecycle 固定点 emit；open session 时 resolve
├── config/
│   ├── profiles.py            # 读 binding；executor 字段=槽选用 plugin provide；可选 extensions
│   └── load_and_lock.py       # resolve → lock 完整图
├── adapters/                  # 变薄：具体协议实现可迁 contrib，门面保留
├── cli/
│   └── cmd_plugin.py          # bora plugin install|list|uninstall|materialize-docs…
├── evidence/ · runtime/ · provider/ · evaluation/
└── registry/                  # Registry 客户端（含 bora.plugin/1）
```

#### B. 本机插件 cache（`bora plugin install` 产物）

**默认根目录：** `~/.bora/plugins/`（可用 env `BORA_HOME` 覆盖为 `$BORA_HOME/plugins`；文档与代码同一常量）。

```text
~/.bora/plugins/
├── index.json                 # 已装列表：plugin_id、version、digest、path、manifest 摘要
└── <plugin_id>/<version_or_digest>/
    ├── plugin.yaml            # 或 bora.plugin.yaml：format bora.plugin/1 + slots
    ├── …                      # 实现载荷
    ├── README.md
    └── skills/…               # 可选；不自动进用户 .agents/skills
```

#### C. 外置插件包（作者仓库 / Hub 内容）

```text
my-plugin/
├── plugin.yaml                # format: bora.plugin/1
│                              # slots: provide / on + 默认 priority
├── src/…                      # 贡献实现（注册到 on/provide）
├── README.md
└── skills/…                   # 可选
```

#### D. L1 Ready

Attempt 镜像构建时 **合并** 各贡献的 `image_contribute` 声明（默认基座 + ACP entry + 已绑定插件 bake）。  
**install 本身不 rebuild 镜像**；Ready 在 prepare/bake。

### 7.2 配置职责分层（勿把 profiles 写成全槽清单）

| 工件 | 写什么 | 不写什么 |
| --- | --- | --- |
| **插件 manifest** | 我能贡献哪些槽、默认 priority | 某个 Dataset 用不用我 |
| **install** | 贡献进入本机注册表（可用） | 自动改项目 profiles |
| **profiles binding** | **短意图**：executor 槽选哪个插件的 provide；可选 extensions 覆写 | 抄写该插件全部 slots |
| **lock** | resolve 后的 **完整扩展点图**（运行真相） | 人手维护的配置源 |

### 7.3 profiles 字段（终态形状）

**概念分层（易混，验收必清）：**

| 概念 | 是什么 | 不是什么 |
| --- | --- | --- |
| **扩展点 `executor`** | 宿主上的 **槽**（单赢家 provide） | 插件本体 |
| **插件 `nooa` / `acp`** | 贡献方；manifest **声明** provide/on 哪些槽 | 与 `executor` 字段本体论等同 |
| **profiles 的 `executor:` 值** | 兼容字段：本 binding 的 **executor 槽** 选用 **哪个 plugin_id 所 provide 的实现** | 「executor 就是 plugin」 |

校验通过：注册表里该 `plugin_id` **已对槽 `executor` 做过 provide**；否则 resolve fail closed。

**日常写法（兼容字段）：**

```yaml
format: bora.profiles/1
bindings:
  solver:
    # executor 槽 ← 使用 nooa 插件 provide 的实现（nooa 须已声明 provide executor）
    executor: nooa
    model: glm-5.2
    api_key: glm_coding_api_key
    options:
      agent: "lib.agents:JsonlAggAgent"   # package 任务程序，非插件 manifest
      method: "run"
  user:
    executor: acp                  # 另一 binding：executor 槽用 acp 的 provide
    options:
      entry: pi
```

等价显式（slot 与 plugin 分开写，与上式同义）：

```yaml
  solver:
    extensions:
      - slot: executor
        plugin: nooa
```

**仅在需要时追加覆写：** 消歧、priority、`replace_default`、或启用无 `executor:` 可表达的纯 hook 插件。

```yaml
  solver:
    executor: nooa
    extensions:
      - slot: before_agent_invoke
        plugin: my-audit
        priority: 20
      - slot: trajectory_seal
        plugin: my-seal
        replace_default: true
```

**规则：**

- `executor: <plugin_id>` = 语法糖：槽 `executor` 选用该插件的 provide；**不是** 两概念绑成一体。  
- 插件还可贡献其它槽；默认靠 manifest 注册 + priority，**不必** profiles 抄全槽。  
- 多 binding 可并存（solver 的 executor 槽用 nooa 贡献，user 用 acp 贡献）。  
- harness 只 `session(profile_id)`，不读插件类型。

### 7.4 lock 完整图（运行真相 · 验收必查）

由 **resolve 生成**，不是手填配置。示意：

```json
{
  "extension_bindings": {
    "solver": {
      "executor": {
        "kind": "provide",
        "plugin": "nooa",
        "version": "0.1.0",
        "digest": "sha256:…",
        "priority": 10,
        "source": "profile_executor_field",
        "replaced_default": true
      },
      "before_agent_invoke": {
        "kind": "on",
        "chain": [
          {"plugin": "my-audit", "priority": 20, "source": "explicit"},
          {"plugin": "default", "priority": 1000, "source": "default"}
        ]
      }
    },
    "user": {
      "executor": {
        "kind": "provide",
        "plugin": "acp",
        "source": "profile_executor_field"
      }
    }
  }
}
```

**语义：**

- 顶层按 **profile_id / binding id** 分图（多 agent 绑定并存）。  
- `executor` 为 **单赢家**（该 binding 一次 invoke 只跑一个实现）。  
- 链槽为 **chain 数组**（可含 default + 多插件）。  
- run 必须使用与 lock 一致的 digest/图（或等价再 resolve 且与 lock 比对一致）。

### 7.5 `bora plugin install` 落盘与不落盘

| 落点 | install 是否写 | 说明 |
| --- | --- | --- |
| `~/.bora/plugins/index.json` | **是** | 已装索引 |
| `~/.bora/plugins/<id>/<ver>/` | **是** | 包内容 + manifest |
| 项目 `profiles.yaml` | **否** | 安装 ≠ 自动切换 binding |
| `bora.yaml` / `task.yaml` | **否** | 同上 |
| lock | **否（当下）** | 下次 lock/run 且 profiles 指向该插件时写入图 |
| `.agents/skills` | **否（默认）** | 仅显式 materialize 命令 |
| L1 镜像 | **否（当下）** | Ready 在 prepare/bake |
| 远端 Hub | path install **否** | hub install/publish 另论 |

**install 后立刻可观察：** `plugin list`、Recognition（executors 清单）、cache 文件存在。

### 7.6 Resolve 与正确调用链路（必读）

**目标：** 保证 `session(profile_id).invoke` 调到 **该 binding 解析出的** SPI 方法，而非字符串乱反射、而非 harness 选类。

```text
① 注册阶段（进程启动默认 + plugin install 加载）
   provide("executor", plugin_id="nooa", impl=NooaExecutor|factory, priority=…)
   on("before_agent_invoke", plugin_id="audit", fn=…, priority=…)
   → Registry 持有「可调用对象 / factory」，不是裸类名碰运气

② open session(profile_id) 时（推荐钉死一次，勿每 invoke 漂移）
   intent = profiles.bindings[profile_id]
     # 含兼容字段 executor:<plugin_id> → 展开为「槽 executor 选用该 plugin 的 provide」
     # 校验：Registry 中该 plugin 必须已 provide(executor)，否则 fail closed
     # 另含可选 extensions 覆写其它槽
   graph  = resolve(intent, Registry, conflict_rules)
   session.extension_graph = graph         # 钉死本 session
   （lock 时对每个用到的 profile 同样 resolve 并写入 extension_bindings[profile]）

③ open_session / close_session（#71 A）
   open:  resolve+pin → before_agent_open → after_agent_open（fail closed）
   close: before_agent_close → executor.close → after_agent_close（fail-open 可记录）

④ invoke(prompt)
   prompt2 = run_chain(graph, "before_agent_invoke", prompt)   # 串行 next，可改写
   result  = await graph.providers["executor"].invoke(…)      # 该槽赢家的 SPI
   result2 = run_chain(graph, "after_agent_invoke", result)
   result3 = run_chain(graph, "normalize_agent_result", result2)
   seal:   trajectory_collect → trajectory_enrich → write trajectory.jsonl(from payload)
           → trajectory_seal provide → evidence_extra

⑤ env prepare / teardown（#71 C — 可执行 SPI，禁止声明式 command 行）
   after seed: run_chain(env_prepare_commands, env_doc, ctx=live)
               run_chain(env_inject, env_doc, ctx=live)
               providers[env_action] → optional EnvironmentManager.action_gate
   teardown:   run_chain(env_teardown_commands, …) → close

⑥ evaluate（#71 D）
   evaluation_input_contribute → evaluation_runtime provide → evaluator
   → score_postprocess（改分语义须进 lock extension_bindings）

⑦ harness
   仅 session(profile_id).invoke — 零插件 import

**反模式（否决）：** 插件只往 list 里 append `{kind: shell, argv: …}`，指望 Core 事后解释。
正确：handler 在 `next` 链上 **自己执行** 副作用或改写 value。
```

**多 binding 并存：**

| 调用 | 图 |
| --- | --- |
| `session("solver")` | 仅 solver 的图（executor 槽可能是 nooa 的 provide） |
| `session("user")` | 仅 user 的图（executor 槽可能是 acp 的 provide） |

**正确调用的三道锁：**

1. 注册时写入 **SPI 兼容** 的 impl/factory；  
2. resolve 只从 Registry **按 plugin_id + 冲突规则** 取；  
3. invoke 只调 **graph 上对象** 的标准方法（open/invoke/close 或 handler(next)）。

**executor 槽：** 该 binding 上只跑 **一个** provide 实现（来自某个插件的贡献，不是一次 invoke 跑两个）。  
**链槽：** 默认可与多插件 **串行** 并存。

### 7.7 端到端验收句（全主题）

1. 目录具备 §7.1 分层（`src/bora/plugins/` 内核 + defaults + contrib/acp + cli + `~/.bora/plugins` cache）。  
2. 仅装 BORA、默认 profiles → ACP 主路径可 run；lock 图含 default/acp 贡献。  
3. `plugin install` 只改 cache/index，不改 profiles；list + Recognition 可见。  
4. profiles `executor: nooa`（槽选用 nooa 的 provide）且 nooa 已注册 provide(executor) → lock 中该 profile 的 executor 槽记录 plugin=nooa@digest；harness 无 diff。  

5. solver=nooa 与 user=acp 可同 profiles 并存；各自 session 调各自 graph。  
6. 同槽平局无显式绑定 → fail closed。  
7. 显式 `extensions` 仅用于覆写/消歧时生效且进 lock。

---

## Invariants

- 开发基线分支：**canary**（本主题从 canary 拉分支、合回 canary）。  
- **MVP：不向后兼容；删除优先于胶水**（见 §0）。  
- 主模型 = 扩展点 + 注册表（链 / 单赢家）。  
- **L0–L5 全部公开**；L3 改评测必须进 lock。  
- 链槽允许中间件改写；默认贡献可被合法卸/替。  
- 冲突：**显式绑定 > priority**；平局 fail closed。  
- 绑定意图：**扩展 profiles（短）**；真相：**lock 完整图（按 profile 分图）**。  
- 插件包：**bora.plugin/1** + manifest slots；**profiles 不抄全槽**。  
- 默认注册保证「仅装 BORA」时 ACP 主路径可跑。  
- harness 不引用插件类型；**按 profile_id resolve 并钉死 session 图**。  
- Recognition ≠ Ready。  
- 主分发 Hub+CLI。  
- 验收证据以 **§7** 为准。

---

## Alternatives considered

| 选项 | 否决原因 |
| --- | --- |
| 插件继承整条 Runtime 作主模型 | 难多插件同点；与优先级/lock 别扭；易误导到 harness 写插件类 |
| 仅 pip entry point 作产品真相 | 与 Hub 分发分裂；Recognition≠Ready 心智差 |
| 无默认全靠插件 | 主路径过险 |
| 仅公开小子集（旧稿） | **已否决**：终态要求 L0–L5 全公开 |
| 全量 ACP 外置插件包 | 与默认 fallback 主验收冲突 |
| 独立 bindings 文件为真相 | **已否决**：终态用扩展 profiles + lock 展开 |
| profiles 抄写插件全部 slots | **已否决**：manifest 声明能力；profiles 只意图/覆写 |
| 全局 task 只能选一个 executor | **已否决**：per-binding 图；多 profile 可混用 |
| 把 `executor:` 字段值当成「executor≡plugin」 | **已否决**：字段是槽选用贡献方的语法糖；插件 provide 该槽才合法 |
| 新注册表与旧 resolve_executor 双轨并存 | **已否决（MVP）**：删除旧路径；不写兼容胶水 |

---

## History

| Date | Change | Reason |
| --- | --- | --- |
| 2026-08-11 | Initial（扩展点+注册表） | 对齐写法 B |
| 2026-08-11 | 补 Background；标明 canary 基线 | 自包含背景 |
| 2026-08-11 | 终态拍板六项写入 Decision | L0–L5 全公开；链可改写；冲突规则；profiles+lock；默认可卸；bora.plugin/1 |
| 2026-08-11 | §7 验收目标证据 | 目录树、profiles 短绑定、install 落盘、resolve 链路、多 profile 并存 |
| 2026-08-11 | §7.3 澄清 executor 字段 | `executor: nooa` = 槽选用插件的 provide，非 executor≡plugin |
| 2026-08-11 | 宿主包名 `extension/` → `plugins/` | 与产品「插件」用语对齐；cache 仍为 `~/.bora/plugins` |
| 2026-08-11 | §0 MVP 实现纪律 | 不向后兼容；删除优先于胶水；禁双轨 fallback |
| 2026-08-11 | 纠正 nooa 形态 | nooa **不得** first-party；须外置 `bora.plugin/1` + install；仅 ACP 为默认 first-party 专有 |
