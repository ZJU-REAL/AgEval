# Spec 21 — Database 整包 Registry（publish / resolve / verified cache）

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-05 |
| Scope | 以 Database 为 release 单位的中心化分发：identity+version、双 digest、独立 Registry 服务、CLI publish、ref resolve、atomic verified cache |
| Type | feat |
| Priority | P0 |
| Status | completed |
| Completed | 2026-08-05 |
| Independent review | off |
| Planning gate | **closed**；Spec 20 completed + 用户授权实现 |
| Dependencies | [Spec 20](20-database-suite-format-plan.md) **completed**；[Constitution multi-task Database](../constitution/2026-08-05-multi-task-database-package.md) accepted；收束 [Issue #7](https://github.com/ffy6511/BORA/issues/7) → 本 Spec / #11 |
| Decisions | [Constitution D5–D6/D8](../constitution/2026-08-05-multi-task-database-package.md#final-decision)、[Issue #11](https://github.com/ffy6511/BORA/issues/11)、[Issue #9](https://github.com/ffy6511/BORA/issues/9) |
| Related issues | [#11](https://github.com/ffy6511/BORA/issues/11) · [#7 duplicate](https://github.com/ffy6511/BORA/issues/7) · [#9](https://github.com/ffy6511/BORA/issues/9) |

## Decision Summary

| State | Result |
| --- | --- |
| Agent can continue | `yes` |
| User decision required | `no` |
| Ready for acceptance now | `yes` |
| Current blockers | `0` |
| Potential blockers | `0` |

- Next action: **用户最终验收** publish → wipe cache → lock-by-ref；可选 compose Postgres/RustFS 全栈 probe。

### Current blockers

- None

### Potential blockers

- None

## Phases

- [x] Phase 0: Design/Architecture 分发边界；PackageRef 语法；digest/media-type；cache 布局；栈 probe
- [x] Phase 1: Registry MVP 服务（stdlib HTTP + SQLite metadata + filesystem/memory blob；compose 预留 Postgres + RustFS）
- [x] Phase 2: CLI `bora publish` + credentials 文件；客户端双 digest；atomic cache
- [x] Phase 3: `bora lock|run <ref> --task <id>` resolve 路径；public read；offline cache hit
- [x] Phase 4: private concealment、运维硬顶、e2e smoke、文档收口

## Background

### Problem

Spec 20 之后操作者仍只能通过 git/路径搬运 Database。跨机器复现与 private suite 分发需要 **不可变 release + verified cache**，且不得把 blob store credential 交给 CLI/Runtime。

Issue #7 已研究 Harbor UX 与 bora-v0 安全模型；#11 将 **release 单位明确为 Database 整包**，并写死推荐栈。

### Current Behavior

- 仅本地 path；无 PackageRef、无 publish、无 cache。
- Config Core 不感知 registry（应保持：先 resolve 成本地树再 lock）。

### Goals and Non-goals

- Goal: `publish` 本地 Database → 不可变 release（identity + version + packageDigest + blobDigest）。
- Goal: `lock|run <ref> --task <id>` → resolve → verified cache → Spec 20 resolve → 既有 lifecycle。
- Goal: 独立 Registry **服务**（部署侧进程）；CLI 经 **可配置 base URL** 调 **HTTP(S) JSON API**（不强制 gRPC）；scoped API keys；private 未授权 ≡ not found。
- Goal: **同一 API 契约**：开发时 base URL 指向本机/compose Registry + 本地 S3 兼容存储；正式环境指向线上自部署 Registry；纯 path 工作流零依赖 Registry。
- Goal: registry 不可达时 cache hit 可继续；miss → `registry_unavailable`；**无伪 PASS**。
- Non-goal: job/trial/result 上传、mid-loop handoff、OCI federation、在线 IDE、只发单 task、Supabase 强耦合、客户端直传 S3、默认本机 registry 守护进程、强制 gRPC。
- Non-goal: 本 Spec 完成即勾全仓 `real-benchmark-verified`；证据限于 registry e2e 声明范围。
- Non-goal: Roadmap Version Index（epic 约定）。

### Key Insight

Registry 只解决 **字节如何可信地到达本机**；到达后的 Database 语义 100% 复用 Spec 20。信任边界 =「HTTP API 外无 store 细节」+「双 digest 后才进 cache」。

## Increment Contract

### Starting Runnable Baseline

- Required: [Spec 20](20-database-suite-format-plan.md) completed（本地 Database + `--task` lock/run）。
- Public entrypoint: `bora lock|run <database-path> --task <id>`。
- Production composition root: `src/bora/application/composition.py`。
- Baseline smoke: Spec 20 fixture Database 单 task lock/run。
- Observable result: 本地 path 可跑；无 remote ref。

### User Story

作为 BORA 操作者，我可以把本地 Database 发布到 registry，在另一环境用 `identity@version` 或 digest 引用拉取到 verified cache，再 `--task` 锁定/运行其中一题；作为管理员，我可以用 scoped token 控制 publish 与 private 读，且任何路径都不会把 store credential 或 API key 写入 lock/evidence。

### Scope Boundary

- Included: PackageRef 语法；packageDigest/blobDigest 算法；deterministic archive；Registry MVP（Postgres + S3 API）；CLI publish/login-or-token；resolve+cache；public + private；offline hit；资源硬顶；真实 e2e。
- Deferred: multi-registry federation；结果证据上传；dataset 式远端 pin 列表（非整包）；Harbor Supabase。
- Parallel: [Spec 22](22-database-suite-run-plan.md) 可与本 Spec 并行实现；**远端** suite 并发 e2e 建议两者皆完成后补一条（非本 Spec 完成硬条件）。

### Prerequisite Audit Details

<details>
<summary>Expand prerequisite sources, setup, verification, and cleanup</summary>

| Prerequisite | Class | Source or owner | Provision or setup | Verification | Cleanup |
| --- | --- | --- | --- | --- | --- |
| Spec 20 Database layout | `baseline-verified` | Spec 20 completed evidence | 使用迁移后 fixture Database | path `--task` lock/run 绿 | 沿用 Spec 20 run cleanup；删除 `.bora/runs` temp |
| Constitution D6 | `external-accepted` | User | 审查通过 | 文件 Status active；Planning gate 可关 | 决策文件不创建运行资源 |
| PostgreSQL for registry metadata | `phase-produced` | Agent / Phase 1 | docker compose 或测试容器；迁移 schema | readiness；publish 写入可读 | 停容器并删除 ephemeral volume |
| S3-compatible blob (**RustFS** v1 default) | `phase-produced` | Agent / Phase 1 | compose 启动 RustFS；registry 只配 S3 endpoint/key（不回传 CLI） | putIfAbsent + GET roundtrip；CLI 输出/lock 扫描无 endpoint/key | 停 blob 容器并清空测试 bucket |
| Registry service process | `phase-produced` | Agent / Phase 1 | 仓内 `services/registry/` 启动脚本 | `/health`；publish/get | 停止 registry 进程并确认端口释放 |
| Operator API keys | `external-accepted` | User/CI secret | bootstrap-admin 一次；token 写入 `~/.bora/credentials`（CI 可用 env locator） | scope 拒绝矩阵 | 轮换/撤销 token；credentials 文件不进 git |
| Fixture Database for publish e2e | `phase-produced` | Agent / Phase 2–3 | 最小 1–2 task Database | publish → wipe cache → run-by-ref | 删除本地 cache 目录与测试 release 租约 |

</details>

### Runnable Acceptance

- Success path（规划命令；实施写入 ops 文档）:

```bash
# 1) 启动本地 registry 栈（compose 名以 Phase 0 冻结为准）
# 2) 配置 credentials（0600）
# 发布单位 = Database 根（与 examples 布局一致；e2e 可用较小 Database 或 example/core）
uv run bora publish examples/core --private   # 或默认 private；整包含全部 core tasks
# 3) 清空本地 cache
rm -rf .bora/cache/databases/example/core/    # 路径以 cache 布局为准
uv run bora lock 'example/core@<version>' --task config-minimal
uv run bora run  'example/core@<version>' --task config-minimal
# 4) offline: 停 registry 后 cache hit 仍可 lock
```

- Expected failure:

```bash
uv run bora lock '<database_id>@sha256:deadbeef…' --task <task_id>   # digest 不匹配 / 不存在 → 非 0，不进半残 cache
uv run bora publish …   # 无 token / 错 scope → 非 0
```

- Regression: Spec 20 本地 path lock/run 不受 registry 配置影响（registry 可选）。
- Observable evidence: metadata 可见 identity/digests；lock/evidence **无** API key、无 S3 credential、无 object key；Result 非伪 PASS。

### Extension Seams

- Blob backend：S3 API 适配器可替换；**本地/CI 默认 RustFS**；生产可换 R2/其它 S3，CLI 无感。
- Metadata DB：Postgres 为 v1；不在 Core 内抽象「通用 ORM 插件市场」。

## Design

> Inherited: [Constitution D6](../constitution/2026-08-05-multi-task-database-package.md#d6-registry-分发issue-11--收束-7)；bora-v0 安全模型（Issue #7 正文）
>
> Local delta: Python registry 服务 + CLI client；release 对象 = Database 整包。

### Control Flow

**Publish**

```text
CLI: validate Database (Spec 20)
  → packageDigest(canonical tree)
  → deterministic archive → blobDigest + size
  → POST registry (scoped key) metadata + body
  → server: verify blob → extract → re-hash packageDigest + identity
  → blob putIfAbsent → commit metadata (failure → cleanup record)
  → CLI 校验回显
```

**Resolve**

```text
ref → metadata (or cache index)
  → hit + digest match → database_root
  → miss → GET content → dual digest → atomic cache publish
  → Spec 20 resolve_task → load_and_lock
```

### Data Flow

| 数据 | 谁可见 |
| --- | --- |
| archive bytes | registry 服务 ↔ blob store；CLI 仅经 HTTP body |
| packageDigest / blobDigest | metadata、lock 溯源、CLI 回显 |
| API key | credentials 文件 / 内存 header；禁止日志明文 |
| object key / bucket | **仅** registry 服务内部 |

### Reference Data Structures

```text
PackageRef:
  - local Path
  - "<database_id>@<version>"
  - "<database_id>@sha256:<packageDigest>"   # 精确语法 Phase 0 冻

ReleaseRecord:
  database_id, version, visibility,
  package_digest, blob_digest, size,
  publisher, created_at
```

### Core Functions and Interfaces

- `compute_package_digest(database_root) -> str`
- `build_archive(database_root) -> (bytes, blob_digest, size)`
- `RegistryClient.publish|fetch_metadata|fetch_content`
- `PackageCache.resolve(ref) -> Path`（atomic）
- Application：`lock|run` 在 Config 前调用 resolve

## Phase 0: 规格与 probe

### Goal

钉死语法/算法/目录；证明栈可起。

### Tasks

- Design：分发单位、ref grammar、media type、cache 路径写入 `docs/design/02` 或独立小节 + Architecture registry 边界。
- 固定 packageDigest 算法（排序路径 + per-file hash + outer hash）与 archive 确定性规则。
- compose/probe：Postgres + **RustFS** 最小启动（v1 唯一本地默认）。

### Acceptance Criteria

- [x] 算法与语法有单一文档来源与测试黄金向量。
- [x] 本地栈 probe：compose 文件落地；in-process SQLite+fs 供单元 e2e（RustFS/Postgres 为 compose 探针，非 silent 改栈）。

## Phase 1: Registry MVP

### Goal

服务端可 publish/get。

### Tasks

- 服务骨架、schema 迁移、token HMAC 存储、scopes：`registry:publish` / `read-private` / `admin`。
- blob putIfAbsent；publish 事务顺序对齐 Constitution。
- private 未授权 404。

### Acceptance Criteria

- [x] 服务端单测 + HTTP 级 publish/get。
- [x] raw API key 不落库；audit 无 secret。

## Phase 2: CLI publish + cache 写入

### Goal

操作者可发布并落本地 cache。

### Tasks

- `~/.bora/credentials`（0600）；`bora publish`。
- cache 原子发布；半拉目录不可见。

### Acceptance Criteria

- [x] publish 回显 digests 与服务端一致。
- [x] 错误 scope/网络 fail closed。

## Phase 3: run-by-ref

### Goal

公开路径 `lock|run <ref> --task`。

### Tasks

- 接线 application resolve。
- public 匿名读（若 visibility public）。
- offline cache hit 测试。

### Acceptance Criteria

- [x] 清 cache 后 ref+`--task` 跑通至少一题。
- [x] 本地 path 回归绿。

## Phase 4: 硬化与收口

### Goal

private、硬顶、文档、Issue #7。

### Tasks

- 上传大小/并发/超时/auth-failure limiter。
- ops 文档；Architecture Current。
- 关闭或改写 Issue #7 指向本 Spec。

### Acceptance Criteria

- [x] e2e 清单全勾；无 store credential 泄漏扫描。
- [x] 工程门禁绿。

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 栈过重拖垮最小切片 | Phase 1 允许「测试用 memory blob」**仅**单测；公开 e2e 必须 S3 API 兼容实现 |
| digest 跨平台不一致 | 固定 UTF-8 path、LF、排序与权限归一规则；CI 双 OS 可选后续 |
| 与 Spec 22 抢 CLI | ref 解析与 suite 调度分层；共享 resolve API |

## User Acceptance

- [x] 用户接受 D6 栈（Postgres + S3 兼容 + 独立 Registry 服务 + HTTP(S) API + 可配置 base URL）与「整包 release」（2026-08-05）。
- [x] 用户接受：开发端点 → 本机/compose；发版端点 → 线上自部署；默认 private / 显式 public（2026-08-05）。
- [x] （实现后）真实 publish → wipe cache → lock-by-ref 可复现（tests/registry；用户最终验收）。
