# 05 — Runtime Core（stub）

| 字段 | 值 |
| --- | --- |
| 产品 | Bounded Orchestration for Runtime Agents（BORA） |
| 状态 | **已拆分** — 正文迁至 [`05-runtime/`](05-runtime/) |
| 保留原因 | 兼容历史链接（`docs/design/05-runtime-core.md` 及旧 §8.x 书签） |

---

## 请改读

Runtime 稳定设计已按执行链拆分为子文件：

| 主题 | 路径 |
| --- | --- |
| 索引与边界 | [05-runtime/README.md](05-runtime/README.md) |
| Lifecycle | [05-runtime/lifecycle.md](05-runtime/lifecycle.md) |
| Provider / L1 | [05-runtime/provider-l1.md](05-runtime/provider-l1.md) |
| Agent Service / ACP | [05-runtime/agent-service.md](05-runtime/agent-service.md) |
| Environment | [05-runtime/environment.md](05-runtime/environment.md) |
| Evaluation / Result | [05-runtime/evaluation.md](05-runtime/evaluation.md) |
| Evidence / trajectory | [05-runtime/evidence.md](05-runtime/evidence.md) |
| Campaign / Suite | [05-runtime/campaign-suite.md](05-runtime/campaign-suite.md) |

### 主题 → 子文（常用）

| 主题 | 路径 |
| --- | --- |
| Lifecycle / 外层状态机 | [lifecycle.md](05-runtime/lifecycle.md) |
| Provider / L1 | [provider-l1.md](05-runtime/provider-l1.md) |
| Agent Service / ACP | [agent-service.md](05-runtime/agent-service.md) |
| ACP inlet | [agent-service.md](05-runtime/agent-service.md#acp-作为-coding-agent-统一-inlet) |
| Environment | [environment.md](05-runtime/environment.md) |
| Evaluation / Result | [evaluation.md](05-runtime/evaluation.md) |
| Evidence / trajectory | [evidence.md](05-runtime/evidence.md) |
| Campaign / Suite | [campaign-suite.md](05-runtime/campaign-suite.md) |

设计原则：`docs/design` 写稳定机制，不写实现进度。实现缺口见 [GitHub Issues](https://github.com/ffy6511/BORA/issues)。
