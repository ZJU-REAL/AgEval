# 14 — Agent Hub 与 `bora.agent/1`

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | 本文件与同目录其它 design 文档共同构成设计权威 |
| 摘要 | 一等 Agent 对象：`bora.agent/1` 包格式、本地缓存与 Hub 地址、`--agent` 投影进 profiles 通道、通配 `"*"` 默认绑定、`agent_ref` 溯源非身份、Registry `package_kind=agent`、Hub Agents 页与 plaza 互链 |

---

## 模型

**Agent** 是可发布、可拉取、版本化的 **job 绑定配置对象**：恰好一条 `bora.profiles/1` binding（executor / model / options / extensions / locator），加显示元数据。它回答「怎么跑一个 agent」，与 Dataset（「测什么」）和 plugin（「机制怎么实现」）正交。

| 对象 | 回答 | 交付单位 |
| --- | --- | --- |
| Dataset（`bora.database/1`） | 测什么（task 身份 + evaluator truth） | 包 |
| Plugin（`bora.plugin/1`） | 机制怎么实现（executor / 槽位 handler） | 包 |
| **Agent（`bora.agent/1`）** | **怎么跑一个 agent（binding 选型）** | 包 |

Agent **不是**新的执行机制：运行期它只是投影成一份 profiles 绑定,走既有
`resolve_profile_bindings` → `merge_bindings_onto_slots` → `job_overlay` → lock digest / suite fingerprint 通道。Config Core 之下无新分支。

## 包格式 `bora.agent/1`

包根 `agent.yaml`（可伴随 `README.md` / `docs/`；**不含**其它运行时文件）：

```yaml
format: bora.agent/1
agent_id: swe-codex-high        # ^[a-z0-9][a-z0-9_-]*$；Hub 地址为 org/agent_id
version: "0.1.0"                # publish 必填；进 lock 溯源
label: "Codex · GPT-5.4 · high" # 显示名；binding 未给 label 时下沉为 binding.label
description: "…"                # 可选
tags: [coding, swe]             # 可选 list[str]
binding:                        # 恰好一条 bora.profiles/1 binding；同一校验器
  executor: acp
  model: gpt-5.4-mini
  extensions:
    - plugin: acp
      options: { entry: codex, reasoning_effort: high }
  api_key: openai_api_key       # env locator 名 only；出现 secret 值 → fail closed
  # base_url / options / overlays 同 profiles binding 语义
```

| 规则 | 说明 |
| --- | --- |
| 顶层 allowlist | `{format, agent_id, version, label, description, tags, binding}`；未知键 fail closed |
| binding 校验 | 复用 profiles 的 binding 键 allowlist（`BINDING_FIELD_KEYS`）与 options denylist；**禁止**手写 `binding.agent_ref`（保留键，投影时注入） |
| `binding.overlays` | 允许声明；路径仍按**运行 Database 根**解析（`overlays/` 前缀 + lock fail-closed 扫描,见 12）。Agent 包本身不携带这些字节 |
| secret | 包内全部文件过 overlay 同款 secret 扫描（PEM / token / 高熵）;publish 与 install 双侧 fail closed |
| 单 binding | 一个 Agent = 一个可运行 actor 产品;多角色组合是运行期事（多个 `--agent role=ref`） |

## 地址、缓存与 install

与 plugin 的双地址规则（11 §两套地址）同构：

| 动作 | id / 地址 |
| --- | --- |
| 路径安装 `bora agent install ./my-agent/` | `agent.yaml` 短 id；index 记 `local/<agent_id>`;不访问 Registry |
| `bora agent publish --org acme` | Hub 地址 `acme/<agent_id>`;短 id 拼接,已带 `org/` 前缀须一致 |
| `bora agent install acme/x@1.0.0`（或 `@sha256:…`） | index 记 Hub id + version + digest;**无浮动 latest** |
| `--agent` 引用 | 本地 index 中的 id（`local/x@0.1.0` / `acme/x@1.0.0`）,或**直连文件路径**（开发环） |

缓存布局镜像 plugins：`$BORA_HOME/agents/<id>/<version>/` + `index.json`。
install **只写本地缓存**,永不改写 profiles / task.yaml（同 11 不变量 3）。

## 运行投影：`--agent` → profiles 通道

`bora lock|run|campaign … --agent <spec>`（可重复）;spec 三种形态：

| spec | 语义 |
| --- | --- |
| `<ref>` | 绑定**所有** role 槽（投影为通配键 `"*"`,见下） |
| `<role>=<ref>` | 只绑该 role;与通配可共存,精确优先 |
| `<path>`（目录或 `agent.yaml`） | 直连本地文件,ref 记作 `file:<path>@dev` |

投影器把各 spec 合成**一份 `bora.profiles/1` 文档**(每条 binding 注入 `agent_ref`),
落盘 `<database>/.bora/agent-profiles/<hash>.yaml`,作为 `profiles_path` 进入既有通道 ——
应用层 resolve 调用点零改动。`--agent` 与 `--profiles` **互斥**（都在整体替换 job 绑定）。

### 通配 `"*"` 默认绑定（`bora.profiles/1` 语义扩展）

`bindings` 映射允许保留键 `"*"`：merge 时**先精确 role id,缺则回退 `"*"`**,再走既有缺绑定 fail-closed;`project_job_overlay` 按实际 role id 展开(overlay 内无 `"*"` 残留)。该扩展对手写 profiles.yaml 同样可用(套件内异构 role 拓扑的默认绑定),不改变既有文档的行为。

### `agent_ref`：溯源,不是身份

`agent_ref = "<id>@<version>+sha256:<tree-digest12>"`（本地开发为 `file:<path>@dev+…`）。

| 去向 | 是否包含 | 理由 |
| --- | --- | --- |
| binding 键（`BINDING_FIELD_KEYS`） | ✅ 新增保留键 | 让合成文档可解析、job_overlay 可 round-trip;task.yaml 槽位自动被禁(inline-binding 断言) |
| `job_overlay` / lock digest | ✅ 投影透传 | 运行可归因、可 `results export-profiles` 复跑 |
| suite fingerprint `_ACTOR_KEYS` / plaza `rt_*` | ❌ | **binding 相同的两个 Agent 是同一 runtime**;可比性只看 entry/executor/model/options |

## Registry / Hub

- `package_kind=agent`;media type `application/vnd.bora.agent.v1.tar+gzip`;走泛型 `/v1/packages` 通道(publish / release / versions / files / by-digest),无新路由。
- 服务端 publish 校验：解析 `agent.yaml` + 包级 secret 扫描 + 与 `bora.yaml` / `plugin.yaml` **fail closed 互斥**;产出 binding 摘要(secret-free)供详情页。
- Hub：Agents 列表 / 详情页(binding YAML、版本、文件、install / `--agent` 复跑命令);Dataset 列表继续排除非 database kind。
- Runtime plaza(12)：suite 行 job_overlay 带 `agent_ref` 时,plaza 详情渲染指向 Agent 详情的链接;`rt_*` 身份不变。

## 产品不变量

1. Agent 只是 binding 选型：Config Core 之下**不得**出现 `if agent…` 新分支;投影后与手写 profiles 完全同构。
2. `agent.yaml` 与缓存包内**永不**出现 secret 值;`api_key` / `base_url` 只承载 locator 名。
3. lock 内 agent 引用必须钉死 `version+digest`;**禁止**浮动 `@latest` 进 lock。
4. `agent_ref` 不进 suite fingerprint / `rt_*`;进 `job_overlay` 与 lock digest。
5. `--agent` 与 `--profiles` 互斥;`bora agent install` 只写本地缓存。
6. PASS 仍只来自独立 evaluator;Agent 对象与评分无关。

## 非目标

- **v1 不携带运行时文件**（skills / overlay 字节）：`binding.overlays` 仍指向运行 Database 的 `overlays/` 树。Agent 包内嵌文件并 staging 进 Database 是后续独立设计回合。
- 不做开放商店信任：信任来自 pin + digest + org allowlist 展示策略(同 11)。
- 不引入 Agent 级评分 / 榜单权威:Leaderboard 仍由 suite 结果派生。
