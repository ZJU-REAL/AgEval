# Execution Blockers and Autonomous Decisions

Newest-first log of unanticipated execution choices. Prefer a safe, reversible, in-scope default and continue. Use `awaiting-user` only for missing authority, material irreversible risk, or product/security semantic change. This file does not override Architecture, design docs, or the owning Spec. Current status lives in the Active Spec.

Insert each new entry immediately below the marker. Keep entries short; never record secrets.

<!-- BLOCKED_ENTRIES_START -->

### 2026-08-11 — nooa 误做成 first-party（已纠正 Spec，待改代码）

| Field | Value |
| --- | --- |
| Status | in-progress |
| Spec | [02](active/02-nooa-provide-switch-plan.md) |
| Decision | 产品目标：nooa = **外置插件**；ACP 才 first-party。实现曾把 `contrib/nooa` + bootstrap 默认注册当完成——**偏差**。 |
| Action | Spec 02 重开为 in-progress；终态验收 = path-install 外置 nooa 后 **journeys 四 task 真 `bora run`**。 |
| Owner | 实现 agent（herdr pane grok） |

