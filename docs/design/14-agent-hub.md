# 14 — Agent 对象

format `ageval.agent/1`。不要 `ageval.harness/1`，不要第二套 `package_kind`。`binding.model` 是这次 run 省略 `--model` 时的缺省，不是身份。`base_url` / `api_key` 是 locator，不是包身份，不上 Hub 卡片。

## 两种卡

**机制卡（builtin catalog overlay，不是 upload）。** 与 `/plugins` 内置行同构：`src/ageval/agents/builtin/catalog.json` 手写清单 + 同目录文件树预览。 CLI `--agent pi` 与 Hub 详情共用这棵树。`builtin: true`，无 `org_id`，无 blob / digest / 下载。Registry **不** `import ageval.plugins.contrib`。短 id：

- ACP：`options.entry`（`pi` / `opencode` / `codex` / `claude-code` / `grok-build`）。运输名 `acp` 不是卡。
- 非运输 executor：`openai-http`、`anthropic-http`。
- 环境（`docker` / `local` / `e2b` / `ssh` / `daytona`）不是 Agent 卡。外置 executor（`dsh` / `nooa` / `miniswe`）不自动进清单。

文件树有 `overlays/` 就暴露给包预览；没有就不要造。加卡 = 改 JSON + 过检查脚本，不是 `ageval agent publish`，也不是往 packages 表插行。短 id 保留：publish 撞到 fail-closed。

**定制卡（upload）。** `ageval agent publish` → `org/name@version`。Harness 身份是 executor + ACP entry。缺省 `binding.model`、overlays/files、其余 plugin options（如 `reasoning_effort`）是 run 配方，不是 attach 尺子。

## CLI

`ageval agent install …` 写入 `~/.ageval/agents` 之后，按 `binding.extensions[].plugin` 安装尚未在本机的插件（复用 `ageval plugin install`；只写 `~/.ageval/plugins`）。contrib（如 `acp`）跳过。缺插件或 `host_requires` 不满足则整条 install fail-closed，不把「agent 已装、插件跳过」当成功。不新增 `ageval.agent/1` 字段，不改 profiles / task.yaml。

`--agent pi` 解析仓内机制树（不必 `agent install`）。`--agent org/name@version` 仍是 upload 包。`--agent` 与 `--profiles` 互斥。`--model` 是 run 参数（`lock` / `run` / `campaign`）：先投影 `--agent`，再改已绑角色的 `binding.model`。省略则用包缺省（机制卡可以没有缺省）。不要 `--api-key` / `--base-url`。`ageval results --model` 仍是上传观测标签。不要把 Agent 包当成第二套 lock 权威。

## 溯源与可比性

`agent_ref` 是溯源，不进 `config_fingerprint`。suite 可比性仍含**实际** model 与 secret-free plugin options（`_binding_role_key`）。延后 attach 对齐 executor + ACP entry；**不含** model，也不含其余 plugin options。plaza 规则不变。`local/` 与 `file:` 不能当 Hub 溯源。

## Hub 浏览与 model

`binding.model` 是 invoke id。LiteLLM / OpenCode / DashScope 网关等要带前缀（`dashscope/qwen-max`、`openrouter/deepseek/deepseek-v4-flash`）。Runtime、lock、yaml、CommandStrip `--model` **原样**保留。Hub **不**把 overlay 改写成 catalog slug，也不在 `profiles.yaml` / agent 绑定上加 Hub-only 键。

百科身份是 pin 里的 canonical id（如 `deepseek/deepseek-v4-flash`）。不要 `package_kind=model`，不要 `ageval.model/1`，不要 `/agents/:id/models/:model`。Lab 是 snapshot 分组键，不是 Hub `org_id`。

### Pin

Hub SPA、Registry GET、CI 的请求路径 **禁止** curl models.dev / OpenRouter / Hugging Face / logo CDN。Maintainer 脚本拉一次，提交 versioned snapshot（canonical JSON + lab SVG）。缺 pin：字母标，页面不崩。目录价是该 provider 在 pin 日的 USD/MTok，标成 directory price；不是本 suite 账单，不是 PASS。参数量只在 pin 的 `weights` 是 Hugging Face URL 时可选展示；闭包模型空着。禁止 `@lobehub/icons` 运行时依赖。Lab 标跟 snapshot 走，不进 plugin/agent 闭包 `brand-marks/`。

Pin 可带 `aliases`：overlay **整串** exact → 一条 canonical。Maintainer 改 pin，不是 Hub 表单。Matcher 先吃 alias，再走下面的最长唯一匹配。

### Join（Hub 侧）

Join key = overlay `binding.model` **as run**。不要在 yaml 里剥前缀。

Matcher（确定性，无编辑距离）：

1. pin `aliases` exact。
2. 候选 **最长优先**：整串；再剥 **已知 snapshot provider 前缀**（`openrouter/`、`dashscope/`、`dashscope-`、`openai/`、…）一次或两次（OpenCode 式 `openrouter/deepseek/…`）；再最后一段 `/`；再最后两段 `/`（`deepseek/deepseek-v4-flash`）。
3. 每个候选对 pin 的 canonical id、canonical leaf、provider model id 做 **exact** lookup。
4. **恰好一条** canonical → join。0 或大于 1 → 不自动 join。不要剥到 `flash` / `max`。

`qwen-flash` vs `qwen3.6-flash` vs `qwen3.8-flash`：无 unique hit → 不 join。未 join 的 overlay 仍按原文字渲染（字母标，无百科）。

### `/agents` 与 harness 页

`/agents` Explore：机制卡在前，再是 upload。卡片仍是 harness 包（`CatalogCard`），不是模型。

- 机制卡：plaza overlay 上 `resolve_agent_id` 等于该短 id 的 `model`，受该卡 Performance 采集设置约束（默认 `official`）。Maintainer 可改采集；非 Maintainer 把 suite 挂到内置卡必须走 `agent_performance` 申请。
- 定制卡：同意出场的 `agent_ref` 行（owner attach 或批准 `agent_performance`）。

落地 `/agents/{id}?model=` 是同一详情页 query，值仍是 overlay invoke id（CommandStrip `--model` 可跑；Leaderboard Model 格仍落这里）。二级 **不是** wrapping `Chip`：改成 directory 行（lab 标若已 join、overlay id、canonical 名若已 join、Default 标、suite 数 / pass rate）。canonical 名链到 `/models/{canonical}`。未 join：原样 overlay + 字母标。

Performance **对齐尺子**仍是 harness（executor + ACP entry，**不含** model）。**展示桶**在 join 之后按 canonical；plaza 自动采集用同一 matcher，unique join 不另留前缀孤儿组。机制卡仍不按 agent package version 分组；没有 `agent_ref` 不渲染 version（不要 `unknown`）。定制卡仍按所 attach 的 `org/name@version` 的 version 分组。Share Attach 与 Inbox 的 Model Select 见 [12](12-hub-dataset-and-leaderboard.md)。

### Models plaza

侧栏 **Models**。身份 = pin canonical id。

- `/models`：按 **lab** 分组的 dense directory 行。不要复用 Agent `CatalogCard` 当市场包，不要 Chip。`CatalogScopeBar`：默认 Explore = 全 pin；filter = 已有同意的 Agent Performance。搜索栏下第二条 `UnderlineTabs` 按 pin `modalities` 过滤：All / Text / Image / Video / Transcription（`audio ∈ input`）/ Speech（`audio ∈ output`）。默认 All。行名右侧可叠多枚模态标：纯 text 才出 text 标；其余按 image / video / transcription / speech 各一枚。标的色走现有 `nav-*`（text=`nav-models`，image=`nav-agents`，video=`nav-inbox`，transcription=`nav-datasets`，speech=`nav-plugins`），次底为该色与 canvas 的 `color-mix`，不要新 hex 族、不要 Chip。Tab 选中/hover 只给图标上色，标签走 `body`。
- `/models/{canonical}`：百科（名、描述、family、release、context、modalities、capabilities、open weights、directory price、可选 HF 参数量）+ Appearances（harness + dataset + 观测分）。harness 链 `/agents/{package_id}?model={overlay}`。Eval 事实只来自已有 Agent Performance，不把第三方 bench 和 PASS 混写。`modalities` 是 models.dev 目录声明（input/output：text / image / audio / video / pdf），不是评测事实。

产品禁止 mock-default Agent。
