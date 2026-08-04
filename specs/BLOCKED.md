# Execution Blockers and Autonomous Decisions

本文件是**执行期**意外决策的 newest-first 审计日志，**不是**当前状态面板。

- 当前能否继续、要不要用户拍板：读所属 Active Spec 顶部的 **Decision Summary**。  
- 本文件**不能**覆盖 `docs/`、Architecture、Roadmap 或 Active Spec。若决策改变其中任一权威，必须在同一次变更里改权威文件。  
- 默认：在已接受的 Increment Contract 内选**安全、可逆**路径，记 `resolved-autonomously` 后继续。  
- 仅当需要新权限、重大不可逆风险、或改变已接受产品/安全语义时：`awaiting-user`，并暂停。  
- 用户拍板后：同一条目改为 `resolved-by-user`，勿复制新条目。  
- 不要记录 secret、token、完整堆栈、例行 gate 日志、已知 prerequisite、普通实现选择。  

Allowed status: `resolved-autonomously` | `awaiting-user` | `resolved-by-user`.

Insert each new entry **immediately below** the marker.

<!-- BLOCKED_ENTRIES_START -->

## 2026-08-04T18:00:00+08:00 — Spec 18 implementation authorized

- Status: resolved-by-user
- Spec / Phase: [Spec 18 Phase 0](active/18-l1-multi-agent-docker-scheduling-plan.md#phase-0-sdk-l1-parity--single-actor)
- Blocker: Prior planning gate blocked production code until explicit user authorization
- Decision: User authorized full Spec 18 implementation, Docker/real Agent gates, and Spec completion without ROADMAP edits
- Rationale: User request to execute all phases and run post-completion subagent acceptance
- Impact / Follow-up: L1 multi-actor SDK scheduling landed; Roadmap unchanged; user reviews public smokes
