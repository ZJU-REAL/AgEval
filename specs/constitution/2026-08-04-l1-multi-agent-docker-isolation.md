# 实现决策：L1 多 Agent Docker 隔离与 SDK 调度面

| Field | Value |
| --- | --- |
| Date | 2026-08-04 |
| Owner | User review required (draft from Grok ↔ Codex design discussion via Herdr) |
| Status | **active — user reviewed** |
| Discussants | Grok (parent), Codex agent `bora-l1-design` (Herdr pane) |
| Scope | L1 (`provider.kind: docker`) multi-actor isolation + routing SDK `Agent.session().invoke` into containers |
| Non-scope this file | 改 `src/`、改 design 长文、实现代码 |

## Problem (why this decision exists)

Current L1 vertical slice builds `environment/Dockerfile` and runs Agent effects **in-target** via harness SDK session (non-empty `agent_profiles`).  
Harness SDK multi-profile orchestration works on **L0 host** only. That is **not** the product end-state for L1.

User intent:

1. Harness must schedule via **SDK invoke** under L1 (multi-turn / multi-profile). Runtime must not one-shot Agent.
2. Support **isolation tiers** for multi-agent:
   - **shared-container (low)**: multiple actors, different UIDs, same container; optional shared GID + `shared_write` paths.
   - **container-per-group (stronger)**: one container per logical group (single-actor group ⇒ per-agent container).
3. **agent/actor → docker handle** mapping is a **runtime** fact; YAML declares **logical** topology only.

## Decision

### 1. Scheduling surface (mandatory end-state)

1. **L1 Agent path MUST use the same SDK surface as L0:**  
   `Agent.session(profile_id, actor_id=..., max_turns=...)` → opaque `session_id` → `invoke` / `close`.
2. **ParentAgentService remains the sole authority** for session bind, hard ceilings, trajectory seal, and external Agent effects.
3. **Runtime one-shot `parameters.question` / `workspace_output` Agent path is removed** ([Issue #5](https://github.com/ffy6511/BORA/issues/5)). All business Agent invokes appear in package harness via SDK session when `agent_profiles` is non-empty (no `use_agent_session` flag).
4. **No silent host fallback** for L1 invoke failures (missing binary, dead target, missing credential, relay crash). Fail closed; residual only if package/executor combination is **explicitly unsupported** at lock/prepare (not mid-invoke downgrade).

### 2. Ownership split

| Layer | Owns | Does not own |
| --- | --- | --- |
| **Config / lock** | Isolation **mode**, logical **groups**, **actor** ids, allowed **profile** ids per actor, **shared_write** paths (workspace-relative), attempt-level **network** enum | Docker container IDs, UIDs/GIDs, socket paths, secrets, live handles |
| **Harness** | Workflow, roles, when to open/invoke/close sessions | Creating containers, holding Docker socket, choosing physical targets |
| **Runtime / Provider** | Image build, container/UID topology, credential projection, process group kill, writer-stop barrier, cleanup ledger | Task business messages, PASS |
| **SDK** | Thin client over IPC; opaque session ids | Docker IDs, lock rewriting |

### 3. YAML surface (lock-safe only)

Under `provider` when `kind: docker` and multi-actor isolation is declared:

```yaml
provider:
  kind: docker
  assurance: l1
  network: bridge   # v1: bridge | none — ONE policy for all Agent targets
  # environment/Dockerfile still required (existing decision)
  agent_isolation:
    mode: container-per-group   # or shared-container
    groups:
      - id: analysis
        actors:
          - id: planner
            profiles: [planner-pi]
          - id: reviewer
            profiles: [reviewer-codex]
        shared_write: [workspace/team]   # optional; default []
      - id: worker-a
        actors:
          - id: worker-a
            profiles: [worker-codex]
```

**Validation (fail closed):**

- Every actor id unique; every actor in **exactly one** group; groups non-empty.
- Every `profiles[]` entry references an existing `agent_profiles[].id`.
- `shared_write` paths: relative, no `..`, no absolute, no symlink escape; subset of locked workspace write views for actors in the group.
- L1 session open without `actor_id` → reject.
- Opening a session with `(actor_id, profile_id)` where profile not in actor’s allowlist → reject.
- Executor cannot run under non-root numeric UID for `shared-container` → `unsupported_capability` for that combination (no root/host downgrade).

**Not in YAML / lock:** container id, image runtime handle, uid/gid numbers, docker network name, IPC path, credentials.

### 4. Mapping model

| Map | Visibility | Content |
| --- | --- | --- |
| **Logical** (lock) | Yes | `actor_id` → `group_id` + allowed `profile_id`s + `shared_write`; `mode` |
| **Physical** (Attempt runtime only) | No (private ledger) | `actor_id` → `ExecutionTarget` (`target_id` opaque, docker handle, uid, gid, generation, state) |
| **Session** (runtime) | Opaque to harness | `session_id` → `attempt_id` + `actor_id` + `profile_id` + `target_id` + `generation` |

Rules:

1. **Do not** key containers by `profile_id` alone (multiple actors may share a profile template).
2. **Principal of isolation is `actor_id`.** Profile selects executor/model/credential binding.
3. Docker container IDs live only in Provider cleanup ledger; public evidence may record **opaque `target_id`**, image digest, and **actual isolation mode**.
4. Mapping is **created at Attempt prepare**, not authored in yaml. Yaml only declares the logical topology that prepare materializes.

### 5. Isolation modes (v1 guarantees)

#### `shared-container`

- One Agent container (or one Agent container tree) for the mode’s actors as designed at prepare.
- Each actor: **distinct numeric UID**, **private HOME 0700** (writable cache + projected creds only).
- Same group: optional **shared GID** + write only on `shared_write` paths.
- **Does not claim** independent network namespace or full PID isolation between actors.
- Hardening minimum: no-new-privileges, no docker.sock, actor HOME private, explicit shared paths only.

#### `container-per-group`

- One container per group; single-actor group ⇒ per-agent container.
- **v1: no cross-container shared writable volumes.** Cross-group handoff via publish/materialize only.
- Stronger filesystem boundary than shared-container; still not L2/hostile multi-tenant promise.

### 6. SDK → container call chain (v1)

1. Prepare: build package image; create Harness container + Agent target topology from lock; on any create failure → **do not start harness**.
2. Task worker (process boundary) runs package harness; **only worker** imports harness module.
3. SDK talks to a **worker-local** capability channel (Unix socket / framed relay) that multiplexes open/invoke/close to **parent** ParentAgentService.
4. Harness **never** mounts host Docker socket and never receives raw container handles.
5. `open(actor_id, profile_id)`: Parent validates against lock, binds `ExecutionTarget`, projects **actor-private** credentials for that profile’s executor.
6. `invoke`: atomic hard-ceiling reserve → Provider **exec** into bound target as actor UID/GID with scoped env → trajectory seal → return. No mid-session actor/profile switch.
7. Same session: serialize invokes (v1). Different sessions: concurrent if ceilings allow.
8. `close` / cancel / timeout / worker crash: refuse new effects; kill process groups; fail sessions; Attempt end → writer-stop barrier → remove targets → evaluator barrier.

### 7. Credentials & HOME

1. **Never mount host `$HOME`.**
2. Per actor: empty or projected HOME under attempt-private tree; `CODEX_HOME` / auth files **copy allowlist only**.
3. Concurrent actors **must not** share `~/.codex` / `auth.json` across UIDs.
4. API keys: env locator projection at invoke time; never bake into image layers.

### 8. Network (v1)

1. Single Attempt-level policy for **all** Agent targets: `provider.network: bridge | none`.
2. No per-actor network namespace in `shared-container`.
3. Group-level network is **out of v1**.
4. Harness/evaluator containers remain non-agent network policy as today (eval none).

### 9. Fail-closed matrix

| Condition | Behavior |
| --- | --- |
| Unknown `actor_id` | open fails; no container exec |
| `profile_id` not allowed for actor | open fails |
| Target dead / generation mismatch | invoke fails closed |
| Missing credential for profile | open or invoke fails before CLI start |
| Writer residual after stop | evaluator barrier refuses / Attempt ERROR (existing L1 barrier spirit) |
| CLI unsupported under numeric UID for mode | lock or prepare `unsupported_capability` |
| Any L1 invoke failure | **no** host CLI fallback |

### 10. Mid-loop product / context visibility

| 方案 | v1 |
| --- | --- |
| **A 内存**（harness 序列化进下一轮 prompt；Core unaware） | **采用（默认）** |
| **B Runtime handoff**（immutable materialize） | **延后** → https://github.com/ffy6511/BORA/issues/2 |

- 同进程 loop → A；`shared_write` → 同容器可变协作；跨容器文本 → A（harness 转发）。
- `publish_*` = 终局 artifact；未来 `handoff_*` ≠ PASS 输入。
- 禁止跨容器共享 RW volume；禁止中途正式 PASS。

### 11. Implementation order (guidance, not a Spec)

1. L1 Agent 走 ParentAgentService + in-target exec（单 actor 先）。
2. `agent_isolation` lock + prepare 拓扑。
3. `shared-container` + `shared_write`。
4. `container-per-group`（跨组默认 A 内存）。
5. `parameters.question` Runtime one-shot **removed** (Issue #5); harness-only invoke.
6. Issue #2 handoff（另 Spec）。

## Explicit non-goals (v1 of this decision)

- Dynamic undeclared actors, regroup mid-Attempt, overlapping groups.
- Cross-Attempt container reuse, container-per-invocation, durable reopen.
- Kubernetes / multi-host / L2 malicious tenant claims.
- YAML-declared docker container IDs.
- Control Plane importing/executing task-local harness modules.
- PASS decided by trajectory or harness terminal.
- Mid-loop Runtime handoff（#2，非 v1）。

## Design vs constitution

| Artifact | Must capture |
| --- | --- |
| **This constitution** | Ownership, yaml surface names, mapping rules, fail-closed, no host fallback, isolation mode guarantees, SDK authority |
| **docs/design (later, before implement)** | Detailed IPC framing, Provider `ExecutionTarget`/`exec` API, guarantee matrix, process-group kill contract, evidence fields |
| **Active Spec (later)** | Phased delivery + public smoke/ACs |

## Links

- [docs/design/01-bora-core.md](../../docs/design/01-bora-core.md) Core ownership  
- [docs/design/05-runtime-core.md](../../docs/design/05-runtime-core.md) Provider / Agent Service  
- [docs/design/02-task-package-and-config.md](../../docs/design/02-task-package-and-config.md) package + docker Dockerfile  
- [docs/design/04-harness-core-sdk.md](../../docs/design/04-harness-core-sdk.md) SDK surface  
- Prior constitution: [core-not-bench-adapters](2026-08-03-core-not-bench-adapters.md)  

## Discussion provenance

- Herdr agent: `bora-l1-design` (codex), multi-round design memos (Round 1 ownership/YAML/mapping/IPC; Round 2 tightened after Grok answers on UID, hardening, IPC, cleanup, credentials, network).
- Mid-loop visibility: A-first; handoff → issue #2.
- Parent synthesis: Grok, 2026-08-04.

## History

| Date | Change | Reason |
| --- | --- | --- |
| 2026-08-04 | Status changed to active; downstream design docs and Active Spec authorized for synchronization | User approved this direction for docs/spec sync; implementation remains separately gated |

## Review checklist for user

- [ ] Accept `actor_id` as isolation principal (not profile_id alone)?  
- [ ] Accept yaml `provider.agent_isolation.mode` ∈ {`shared-container`, `container-per-group`}?  
- [ ] Accept docker IDs **runtime-only** (not lock fields)?  
- [ ] Accept “no host fallback” for L1 invoke?  
- [x] Runtime one-shot `parameters.question` removed (Issue #5); harness-only schedule.  
- [ ] Accept §10 mid-loop memory only + #2 deferred?  
- [ ] Any field renames before design doc write-up?
