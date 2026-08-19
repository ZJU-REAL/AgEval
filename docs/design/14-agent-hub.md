# 14 — Agent Hub 与 `bora.agent/1`

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 权威 | 本文件与同目录其它 design 文档共同构成设计权威 |
| 摘要 | 一等 Agent 对象：`bora.agent/1` 包格式、可选 `overlays/` 树、本地缓存与 Hub 地址、`--agent` 投影进 profiles 通道、通配 `"*"` 默认绑定、`agent_ref` 溯源非身份、Registry `package_kind=agent`、Hub Agents 页与 plaza 互链 |

---

## 概念对照(三个易混词)

| 词 | 所在文件 | 是什么 | 类比 |
| --- | --- | --- | --- |
| 角色槽(`agent_profiles`) | 成员 `task.yaml` | 任务身份:声明需要哪些 role id,**禁止**内嵌绑定字段 | 插座 |
| 绑定映射(profiles) | `bora.profiles/1`(库根 / `--profiles` / `--agent` 投影产物) | job 轴:role → binding 的映射表,随 Dataset/本次运行走 | 接线表 |
| **Agent** | `bora.agent/1` 包 | **一条** binding + 身份元数据;版本化、digest 钉死、可发布/拉取、跨 Dataset 复用 | 有版本号的插头 |

运行期恒有:Agent → 投影成 profiles 文档 → merge 到角色槽 → lock 的 `agent_profiles` 行 + `job_overlay`。

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

包根 `agent.yaml`（可伴随 `README.md` / `docs/`；**可**携带 `binding.overlays` 列出的 `overlays/` 树，不含 Dataset / plugin 实现）：

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
| `binding.overlays` | 允许声明；路径形状仍是 `overlays/…`。带 `agent_ref` 时只在已安装 Agent 包下解析；无 `agent_ref` 时仍按运行 Database 根（见下节与 02 / 12） |
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
install **只写本地缓存**,永不改写 profiles / task.yaml（同 11 不变量 3），也永不把 overlay 字节写进 Dataset `overlays/`。

## Agent 包内 `overlays/`

Agent 包**可以**包含一棵 `overlays/` 树。`binding.overlays` 是 publish / install / lock / Hub 关心的路径 allowlist；路径保持 `overlays/…` 形状。未声明 `overlays` 键 = 无树（与今日相同）。

1. **解析根随 `agent_ref`。** 绑定带 `agent_ref` 时，列出的路径以及 `agent-skills` / `home-files` 使用的同一相对 `src` **只**在已安装 Agent 包（`$BORA_HOME/agents/<id>/<version>/`，或 `file:` 直连的包根）下解析。Dataset 同相对路径上的文件**不算**。缺失 → fail closed。
2. **只 materialize 进 Attempt。** Runtime 把列出的文件投影进既有 `home_overlay` dest。**禁止**写入 Dataset `overlays/`（`profiles.yaml` 同级），**禁止**把 overlay 字节写到 `$BORA_HOME/agents/.projections/` 合成 profiles 文档旁边。L1 只投影列出的路径，不把整个 `$BORA_HOME/agents` cache mount 进容器。
3. **无 `agent_ref` 保持 Database 根。** 手写 `--profiles` 仍按运行 Database 根解析 `overlays/`。`--agent` 与 `--profiles` 仍互斥。
4. **不从插件 `options.src` 推断** `binding.overlays`（Core 仍不走插件 options 来构造此列表）。
5. **digest 边界。** overlay 路径与字节仍不进 plaza `rt_*` 或 suite `config_fingerprint`。Agent 包自身的 tree digest **包含**这些文件（它们是包内容）。
6. **复跑。** `export-profiles` 保留 `agent_ref` 与 overlay **路径**。经 `--agent org/id@version` 复跑要求该 Agent 仍已安装。把导出文档再交给 `--profiles` 时，行上仍有 `agent_ref` → 仍只在 Agent 缓存解析；缓存缺失 fail closed，不得用 Dataset `overlays/` 顶替。无 `agent_ref` 的手写 `--profiles` 仍走 Database 根。

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

`bindings` 映射允许保留键 `"*"`,语义为**字段级默认值**:

1. **解析**:某 role 的有效绑定 = 通配行字段 ⊕ 精确行字段(精确覆盖同名字段;`options`/`extensions` 被设置了的精确行整体替换,不做深合并)。两行都缺 → 既有缺绑定 fail-closed。由此 `--set /bindings/<role>/<leaf>` 可对通配绑定做单字段微调而不丢其余字段。
2. **溯源与 overlay 不继承**:`agent_ref` 与 `overlays` 只在该 role 纯由通配覆盖时随通配流动。存在精确行且其未声明该字段时,通配的值 **不** 参与回退——`--agent xx --agent user=yy` 且 `yy` 省略 `overlays` 表示 user **无** overlay 树,不是 xx 的文件挂在 yy 的 `agent_ref` 下。显式改绑过的角色也不归因于该 Agent。
3. **身份**:通配与显式展开是**同一 job 配置**。suite fingerprint 在摘要前把 `"*"` 按任务实际 role id 展开(`project_job_overlay` 与 lock 侧同理),两种写法产生相同 `config_fingerprint`;摘要存储的 `job_overlay` 保留操作者书写形态以保复跑保真。`rt_*` / suite `config_fingerprint` **不得**哈希 overlay 路径或字节。

该扩展对手写 profiles.yaml 同样可用,不改变无通配文档的行为。

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
- Runtime plaza(12)：suite 行 job_overlay 带 `agent_ref` 时,plaza 详情渲染指向 Agent 详情的链接;`rt_*` 身份不变。带 `agent_ref` 的出场预览 `overlays/` 前缀闭包走 **Agent** 包 files API,不走 Dataset release。

## 产品不变量

1. Agent 只是 binding 选型：Config Core 之下**不得**出现按 Agent 产品分支的 executor / lifecycle。投影后与手写 profiles 同构，**唯一**例外是 overlay 解析根：有 `agent_ref` → 已安装 Agent 包；无 → Database 根。
2. `agent.yaml` 与缓存包内**永不**出现 secret 值;`api_key` / `base_url` 只承载 locator 名。
3. lock 内 agent 引用必须钉死 `version+digest`;**禁止**浮动 `@latest` 进 lock。
4. `agent_ref` 不进 suite fingerprint / `rt_*`;进 `job_overlay` 与 lock digest。overlay 路径与字节亦不进 `rt_*` / `config_fingerprint`。
5. `--agent` 与 `--profiles` 互斥;`bora agent install` 只写本地缓存，不写 Dataset `overlays/`。
6. PASS 仍只来自独立 evaluator;Agent 对象与评分无关。

## 非目标

- 不把 overlay 字节拷贝或 staging 进任何 Dataset 树。
- 不实现引擎配置 `files/` + agent 作用域源根（与 `binding.overlays` 分列）。
- 不从插件 `options.src` 推断 `binding.overlays`。
- 不做开放商店信任：信任来自 pin + digest + org allowlist 展示策略(同 11)。
- 不引入 Agent 级评分 / 榜单权威:Leaderboard 仍由 suite 结果派生。
