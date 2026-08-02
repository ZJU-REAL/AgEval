# v1 参考资产与后续样例选型

## 元数据

| 字段 | 值 |
| --- | --- |
| Created | 2026-08-02 |
| Area | feasibility |
| Related | [ROADMAP v0.8/v0.10](../ROADMAP.md)、[docs/design/08](../../docs/design/08-conversion-security-testing.md)、[docs/design/10](../../docs/design/10-examples-database-52.md) |
| Status | open |

## Question

1. v1 归档中哪些测试/Docker/conversion **思路**应在对应 Core/APP 批次移植？  
2. `v0.8` / `v0.10` 的首个真实 upstream 样例优先 terminal 类还是 database-52 类？

## Method

对照 `/Users/zhuo/Developer/Archived/bora-v1` 与本仓 `docs/design/`（**不以 vault 为权威**）。

## Findings

- v1 高价值：隔离红线用例、credential 投影、writer barrier、conversion 正负对照、provenance pin。  
- 不宜搬迁：厚 TaskLocked、YAML 静态 Actor/branch authority、宿主 ToolPort 默认路径。  
- 设计示意 `database-52` 已在 [design/10](../../docs/design/10-examples-database-52.md)；适合在 Core 竖切稳定后作回归，不一定是 `v0.6` 第一样例。

## Recommendation

- 实现期以 v1 为 **oracle checklist**。  
- `v0.6` 用最薄 example + Codex；真实 upstream 样例放到 Core 稳定后的 `v0.8` / `v0.10`。  
- 最终样例 pin 在对应 Active Spec 中确认。

## Open Questions

- 第一真实 upstream 与平台 pin？  
- `v0.9` 第二 AgentExecutor 候选（如 Pi）？  
