# 实现决策：补齐 Core/SDK，禁止按 Benchmark 拟合 Adapter / Version

| Field | Value |
| --- | --- |
| Date | 2026-08-03 |
| Owner | User (explicit, angry correction) |
| Status | active |

## Decision

1. **目标一致：** 为了达到与归档 v1 **同类能力**（workspace 文件任务、多步 Agent、Attempt-local 资源、矩阵等），完善 **BORA Core + Harness Core** 通用契约与实现。  
2. **禁止：** 为 Terminal-Bench / MultiAgentBench / 任一 suite **写专用 adapter**、按 task/domain 分支、或把 Version Index 命名成 `*-bench class`。  
3. **允许：** 用 **薄代表 Task Package**（通用命名）做 public smoke；package 可 *inspired by* v1 oracle，但 Core 不知 bench 名。  
4. **交付槽位：** 优先闭合既有 Roadmap **v0.7–v0.11**（Session/channel、L1 workspace、Environment、Campaign），而不是另起 bench 专属 v0.13/v0.14。  
5. 与 [2026-08-03-critic-checkbox-authority](2026-08-03-critic-checkbox-authority.md) 并存：Critic 过了可勾选；勾选的是 **Core 表面完成**，不是 “bench 接入完成”。

## Links

- [docs/design/01-bora-core.md](../../docs/design/01-bora-core.md) Core 1–5  
- [specs/ROADMAP.md](../ROADMAP.md) Core 能力缺口表  
