# 14 — Agent 对象

format `ageval.agent/1`。一条 binding：executor、entry、overlays。Registry `package_kind=agent`。

CLI：`ageval agent install …` 后 `--agent local/id@version` 投影进 profiles。不要把 Agent 包当成第二套 lock 权威。

产品禁止 mock-default Agent。
