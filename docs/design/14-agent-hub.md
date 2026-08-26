# 14 — Agent 对象

format `ageval.agent/1`。不要 `ageval.harness/1`，不要第二套 `package_kind`。`binding.model` 是这次 run 省略 `--model` 时的缺省，不是身份。`base_url` / `api_key` 是 locator，不是包身份，不上 Hub 卡片。

## 两种卡

**机制卡（builtin catalog overlay，不是 upload）。** 与 `/plugins` 内置行同构：`src/ageval/agents/builtin/catalog.json` 手写清单 + 同目录文件树预览。 CLI `--agent pi` 与 Hub 详情共用这棵树。`builtin: true`，无 `org_id`，无 blob / digest / 下载。Registry **不** `import ageval.plugins.contrib`。短 id：

- ACP：`options.entry`（`pi` / `opencode` / `codex` / `claude-code` / `grok-build`）。运输名 `acp` 不是卡。
- 非运输 executor：`openai-http`。
- 盒子（`docker` / `local` / `e2b` / `ssh` / `daytona`）不是 Agent 卡。外置 executor（`dsh` / `nooa` / `miniswe`）不自动进清单。

文件树有 `overlays/` 就在详情 Binding / Files 展示；没有就不要造。加卡 = 改 JSON + 过检查脚本，不是 `ageval agent publish`，也不是往 packages 表插行。短 id 保留：publish 撞到 fail-closed。

**定制卡（upload）。** `ageval agent publish` → `org/name@version`。身份是 executor、ACP entry、overlays/files、secret-free plugin options。

## CLI

`--agent pi` 解析仓内机制树（不必 `agent install`）。`--agent org/name@version` 仍是 upload 包。`--agent` 与 `--profiles` 互斥。`--model` 是 run 参数（`lock` / `run` / `campaign`）：先投影 `--agent`，再改已绑角色的 `binding.model`。省略则用包缺省（机制卡可以没有缺省）。不要 `--api-key` / `--base-url`。`ageval results --model` 仍是上传观测标签。不要把 Agent 包当成第二套 lock 权威。

## 溯源与可比性

`agent_ref` 是溯源，不进 `config_fingerprint`。suite 可比性仍含**实际** model（`_binding_role_key`）。延后 attach（upload 包）对齐 executor + ACP entry + secret-free plugin options，**不含** model。plaza 规则不变。`local/` 与 `file:` 不能当 Hub 溯源。

## Hub 浏览与 model

`/agents` Explore：机制卡在前，再是 upload。选中后二级 = 已登记 model：

- 机制卡：plaza overlay 上 `resolve_agent_id` 等于该短 id 的 `model`。**不**经 Agent org 同意。
- 定制卡：同意出场的 `agent_ref` 行（owner attach 或批准 `agent_appearance`）。

落地 `/agents/{id}?model=` 是同一详情页 query，不是新路由、不是 combo 包。

产品禁止 mock-default Agent。
