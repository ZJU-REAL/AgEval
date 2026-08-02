# 实现决策：Critic 通过即可勾选 Spec / Roadmap（无需等人验收）

| Field | Value |
| --- | --- |
| Date | 2026-08-03 |
| Owner | User (explicit) |
| Status | active |
| Authority | supersedes prior “Version Index / Spec completion 须用户最终验收才能打钩”操作规则 |

## Decision

1. **Spec 完成情况必须与实现同步更新**（Phase、Acceptance、Engineering Gates、Decision Summary、Implementation Progress、内部 Roadmap 清单）。不得积压到“等人验收”才回写。
2. **勾选权威 = 独立 Critic（或同等 adversarial 评审）通过**，再加门禁证据（公开 smoke / 测试 / 诚实边界）。**不需要**等待用户再点一次验收才打钩。
3. Critic **不通过**时：不得勾选对应完成项；先修代码或诚实回退勾选。
4. 仍禁止：用 fixture 冒充公开证据、假 `assurance:l1` / `isolated`、把草图勾成 Spec 全文完成。

## Scope

- Active Spec checkboxes（Phase / AC / gates / User Acceptance 中已委托 Critic 的项）
- Roadmap 关键交付、验收标准、**Version Index**
- 状态文档中的“当前事实 / 证据等级”与上述勾选一致

## Not changed

- 产品设计仍以 `docs/design/` 为权威；本条只改**完成态勾选的操作权威**。
- Critic 判定“未闭合”的项必须保持 `[ ]` 并写诚实注记。

## Links

- [specs/ROADMAP.md](../ROADMAP.md) 维护规则
- [AGENTS.md](../../AGENTS.md) 交付与证据
