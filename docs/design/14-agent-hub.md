# 14 — Agent 对象

format `ageval.agent/1`。Registry `package_kind=agent`。包身份是 **harness**（executor、ACP entry、overlays/files、secret-free plugin options）。`binding.model` 是这次 run 省略 `--model` 时的缺省，不是身份。不要 `ageval.harness/1`，不要第二套 `package_kind`。`base_url` / `api_key` 是 locator，不是包身份，不上 Hub 卡片。

CLI：`ageval agent install …` 后 `--agent local/id@version` 投影进 profiles。`--agent` 与 `--profiles` 互斥。`--model` 是 run 参数（`lock` / `run` / `campaign`）：先投影 `--agent`，再改已绑角色的 `binding.model`，写入 overlay/lock。省略则用包缺省。不要 `--api-key` / `--base-url`；locator **值**仍走 process env。`ageval results --model` 仍是上传观测标签，不是这条糖。不要把 Agent 包当成第二套 lock 权威。

`agent_ref`（`org/name@version`）是 harness 溯源，不是冻结 model，不进 `config_fingerprint`。suite 可比性仍含**实际** model（`_binding_role_key`）。延后 attach / Appearances 对齐 executor + ACP entry + secret-free plugin options，**不**要求包缺省 model 等于这次 overlay model。plaza 规则不变。`local/` 与 `file:` 不能当 Hub 溯源。Appearances 另需该 Agent 包 org 同意：owner 自己 attach，或批准 `agent_appearance` 请求。

Hub `/agents`：一级 = harness 包。选中后二级 = 该包已登记 model（包缺省 + 同意出场的 overlay model）。落地 `/agents/{package_id}?model=` 是同一详情页的 query（选中该 model、CLI 条带 `--agent` 与 `--model`），不是新路由、不是 combo 包。

产品禁止 mock-default Agent。
