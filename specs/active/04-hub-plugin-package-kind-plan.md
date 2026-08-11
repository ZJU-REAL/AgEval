# Spec 04 — Hub 插件 package：`bora.plugin/1`

## Metadata

| Field | Value |
| --- | --- |
| Created | 2026-08-11 |
| Status | completed |
| Completed | 2026-08-11 |
| Dependencies | [03](03-cli-plugin-lifecycle-plan.md) |
| Decisions | [constitution §2](../constitution/2026-08-11-extension-api-and-registry.md)；包形态 [§7.1C](../constitution/2026-08-11-extension-api-and-registry.md)；install 本地布局 [§7.1B](../constitution/2026-08-11-extension-api-and-registry.md) |

## User Story

作为 **插件作者/操作者**，我可以在 Registry/Hub 以 **`bora.plugin/1`** 发布并预览完整 package，再用 CLI 下载到与 Spec 03 相同的 cache，进入同一套 Registry 加载。

## Acceptance

- [x] **Success smoke：** publish → meta 含 `plugin_preview`（files + slots）→ `plugin install org/id@version` → 本地 index/PKG 符合 §7.1B。  
- [x] **Expected failure：** format 错误（database 冒充 plugin）→ fail closed。  
- [x] **Regression：** Database 包路径不回归（`test_registry_e2e`）；Spec 03 path install 仍可用。  
- [x] **Baseline：** 无 bora.plugin/1。  
- [x] **Engineering gates：** `tests/registry/test_plugin_package_e2e.py`（Hub SPA 未改 UI，API 预览已覆盖 slots/files）。  
- [x] **Docs：** CLI help + media_type `application/vnd.bora.plugin.v1.tar+gzip`；locator `org/plugin_id@version`。  
- [x] **绑定：** 装完 **不** 自动改 profiles（[§7.5](../constitution/2026-08-11-extension-api-and-registry.md)）。

## Scope

- **Included：** format；存储；publish/fetch；完整预览；digest；对接 Spec 03 加载。  
- **Deferred：** 商店排序；强制 ACP 上架；重型审核流。

## 实现思路

### 必读决策

| 主题 | 链接 |
| --- | --- |
| 独立 plugin kind、Hub 预览 | [constitution §2](../constitution/2026-08-11-extension-api-and-registry.md) |
| 插件包目录 | [constitution §7.1C](../constitution/2026-08-11-extension-api-and-registry.md) |
| 本地 cache（下载落地） | [constitution §7.1B](../constitution/2026-08-11-extension-api-and-registry.md) |
| install 不改 profiles | [constitution §7.5](../constitution/2026-08-11-extension-api-and-registry.md) |
| resolve 仍只看本机 Registry + profiles | [constitution §7.6](../constitution/2026-08-11-extension-api-and-registry.md) |
| 本地 install/load 实现 | [Spec 03 实现思路](03-cli-plugin-lifecycle-plan.md) |
| Registry SPI 内核 | [Spec 00 实现思路](00-extension-registry-default-plan.md) |

### 与 Database 的隔离

| | Database | Plugin |
| --- | --- | --- |
| format | `bora.database/1` | **`bora.plugin/1`** |
| 内容 | tasks/harness/… | manifest slots + 实现载荷 |
| Hub 列表 | 现有 | filter format 或分栏 |
| 安装后 | 现有 package cache | Spec 03 plugins cache |

禁止用 database 上传接口无校验地收 plugin blob。

### 服务端（`services/registry`）

1. 上传：校验 `plugin.yaml` format + 必填 plugin_id/version/slots。  
2. 存：blob + 元数据 + content digest（与客户端算法一致，见 Spec 03）。  
3. 权限：沿用 org 成员 / 现有 login 模型。  
4. API：list/get/download；get 返回文件树索引供预览。  
5. 错误：403/404/409(digest)/400(format) 可测。

### Hub（`apps/hub`）

1. 包详情：文件树 + 渲染 `slots.provide` / `slots.on`。  
2. 与 Database 详情组件可复用树，但 format 徽章区分。  
3. 无执行插件代码（只读预览）。

### CLI

```text
bora plugin publish <dir> --org <org>
bora plugin install registry://<org>/<plugin_id>@<version>
# 或 https://… 文档最终只保留一种主 locator
```

流程：鉴权 → 下载 blob → 写入 PLUGINS_ROOT（复用 Spec 03 拷贝/index 逻辑）→ 不改 profiles。

### 与 resolve 的边界

Hub **只分发**。  
切换仍靠 profiles `executor:`（槽选用某插件的 provide）或显式 extensions（[§7.3](../constitution/2026-08-11-extension-api-and-registry.md)）。  
装完未改 profiles：Recognition 有 kind，默认 binding 仍 acp。

### 测试

- registry e2e：publish plugin → download → 本地 load → registry.provide 可见。  
- 负例：database format 当 plugin 上传 → 400。  
- hub 构建（若改前端）。  
- database 回归 smoke。

### 禁止

- 预览或 API 回传 secret。  
- 下载后静默改用户 Database。

## Phases

- [x] Phase 0：Registry 模型 + format 校验（`package_kind` + plugin media_type）  
- [x] Phase 1：publish/fetch + digest（`plugin_package` archive）  
- [x] Phase 2：预览（API `plugin_preview` slots+files；现有 `/files` 树仍可用）  
- [x] Phase 3：CLI publish + remote install + 回归 + Acceptance  

## Evidence

```bash
uv run pytest tests/registry/test_plugin_package_e2e.py tests/plugins/test_cli_plugin_lifecycle.py tests/registry/test_registry_e2e.py -q
```

## Notes

- Hub SPA 未改前端徽章页；预览走 Registry GET meta `plugin_preview` + `/files`（与 constitution「完整预览」API 侧对齐）。若需 UI 徽章可开 follow-up Issue。

