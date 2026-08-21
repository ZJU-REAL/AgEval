# 13 — Web UI 令牌与不变量

适用面:ageval website(landing + docs)、apps/hub、apps/viewer 三个 web 表面的**风格一致性**。
权威顺序:本文件 → 各端令牌定义文件 → 业务代码(只允许引用语义令牌)。
机检:`python3 scripts/check_design_tokens.py`(CI job `design-tokens`),文档表格与脚本内置值**互相校验**,改值必须两侧同步。

## 色彩令牌

色板只有一个品牌强调色:International Klein Blue(IKB)双阶。中性色为冷灰(cool paper / cool ink)。
所有值为 hex,比较大小写不敏感。

| 令牌 | 浅色 | 深色 | 用途 | hub/viewer(`--viewer-*`) | docs(`--color-fd-*`) |
| --- | --- | --- | --- | --- | --- |
| canvas | `#F4F5F8` | `#11141C` | 页面底色 | `canvas` | `background` |
| canvas-soft | `#E8EAF1` | `#1A1E2A` | 卡片 / 悬浮面 / 行 hover | `canvas-soft`、`row-hover` | `muted`(`fd-card` 为本地近似) |
| canvas-soft-2 | `#E4E7F0` | `#222738` | 强填充 / 次级底 | `canvas-soft-2` | `secondary` |
| hairline | `#D5D8E2` | `#2A2F3E` | 分隔线 / ring | `hairline` | `border` |
| ink | `#14161F` | `#EEF0F6` | 标题 / 强文字 | `ink` | `foreground` |
| body | `#4A4E5C` | `#9AA0B4` | 正文 | `body` | `muted-foreground` |
| mute | `#7A7F90` | `#6E7488` | 次要文字 / 图标 | `mute` | — |
| link | `#1B54E8` | `#5B7BFF` | 链接 / 主色 / 焦点(IKB) | `link` | `primary`、`ring` |
| link-deep | `#001F73` | `#8AA0FF` | hover(浅色加深 / 深色提亮) | `link-deep` | — |
| error | `#EE0000` | `#FF5C5C` | 错误 | `error` | — |
| warning | `#F5A623` | `#F5A623` | 警告 | `warning` | — |
| code-bg | `#F4F5F8` | `#0C0E14` | 代码底 | `code-bg` | — |
| accent(landing) | `#5B7BFF`(亮)/ `#002FA7`(深) | 同左 | landing `--accent` / `--accent-deep` | — | — |

landing 的 oklch 系(`oklch(15.4% 0.018 264)` 底等)是本表的 oklch 等值表达,视为同一令牌;
`shell-*` 语法高亮色为 viewer 本地扩展,不跨面。

## 字体

| 角色 | 栈 | 说明 |
| --- | --- | --- |
| sans | `Geist` → `Inter` → `system-ui` → CJK(`Noto Sans SC` / `PingFang SC` / `Microsoft YaHei`) | 全部界面正文;hub/viewer 为系统栈(Geist 命中本地),website 经 next/font 加载 |
| mono | `Geist Mono` → `ui-monospace` → `Menlo` | 代码 / 命令 / 等宽标签 |
| display | `Anton`(wordmark 专用) | 只用于品牌瞬间(hero、logo),**永不**进正文或工具 UI |

## 形状与动效

- **圆角**:6 / 8 / 12px 三档(sm 控件、md 默认、lg 卡片);不发明新档,hero 面板上限 16px。
  按钮走 6px,不要 `clip-path` 切角。
- **动效**:`cubic-bezier(0.22, 1, 0.36, 1)`,默认 200ms。
  Hub / Viewer 只允许 CSS(`ease-smooth`、`data-ageval-pop`);landing 允许一次性 hero stagger 与 8px view-timeline 揭示,进场可到 400ms(强调瞬间,须在 `website/DESIGN.md` 写明)。
  Tooltip 等待 80ms 是意图延迟,不是位移时长。关闭可以快于打开。
  禁止 GSAP / Motion 进三端产品 chrome;landing 也不引入滚动钉住或横向 hijack。
  `prefers-reduced-motion: reduce` 必须落到最终态。
- **焦点**:IKB 是唯一焦点色。按钮 / 链接用 `ring-2 ring-link/70`(landing 3px outline);
  输入框 / select / textarea 只把描边换成 1px `border-link`,不叠 ring。
- **选区**:`::selection` 用 IKB 28% 透明底(三端统一)。
- **深度**:弹层阴影用 `--viewer-shadow-pop` 令牌(hub/viewer);禁硬投影。
  `backdrop-blur` 至多两档(sticky header 用薄档)。

## 组件语汇(应用层)

| 语汇 | 规则 |
| --- | --- |
| 主按钮(SPA Button `default`) | IKB 填充 + `rounded-[6px]` + `font-mono text-[13px] font-semibold` + `focus-visible:ring-2 ring-link/70`,hover `link-deep` |
| 下划线 tab | `UnderlineTabs`:mono uppercase + 滑动 IKB 条(`transform`/`width` 200ms)。不要再复制 `border-b-2` 手写条 |
| Catalog 卡 | 仅 plugin / agent 市场包:`CatalogCard` 12px 圆角、hairline、hover `canvas-soft` + 1px 上移。Jobs / leaderboard / members / datasets 保持表 |
| 页头(PageHead) | h1 + 可选 sub + hairline(无编号 kicker) |
| 相位/耗时图谱 | `--viewer-phase-1..6`(IKB 主导 + 中性梯度),禁 zinc 等外部灰阶 |
| 弹层(tooltip/select/dropdown/dialog) | hairline 边框 + `--viewer-shadow-pop` |
| 危险确认 | Modal：较大标题 + mute 说明后果 + Cancel / Confirm 两枚按钮 |

## 不变量(十条)

1. 色值只允许出现在令牌定义文件与品牌资产(owl 组件);业务代码只写语义令牌名。
2. IKB 只落在链接 / 焦点 / 主 CTA / 品牌位,禁大面积底色(landing ink-banner 例外)。
3. 中性色三层语义:`canvas*` 是面、`hairline` 是线、`ink/body/mute` 是字;`mute` 永不做正文。
4. `Anton` 只做 wordmark;正文一律 sans 栈 + CJK 回退;中文标题粗细上限 semibold。
5. 主 CTA 用 6px 圆角 + IKB 填充;表格 / 输入 / 普通控件用同一套圆角三档。不要切角 `clip-path`。
6. 焦点可见性不妥协。字段用 1px IKB 描边;其它控件用 2px IKB 环
   (landing 3px outline)。
7. 选区、hover、active 的色彩表达一律引用令牌,不自调 hex / opacity 组合。
8. 动效只允许统一缓动曲线;时长偏离 200ms 需要说明理由(landing hero/章节揭示 400ms 是已记录的例外)。
9. 图标两套:品牌用 owl 系列(`owl-flat.tsx` / `OwlIcon`),功能用 lucide;不引入第三套。
10. 深度感不用硬投影;blur 分档封顶,不为单个组件发明新档。

## 品牌资产入口

| 资产 | 位置 | 用途 |
| --- | --- | --- |
| `OwlFlatMark` / `Icon` / `Peek` / `Plate` / `Lockup` / `Watermark` | `website/src/components/owl-flat.tsx` | landing 水印、导航、docs lockup、备用底板 |
| `OwlIcon`(全身) | `apps/hub/src/components/owl-icon.tsx`、`apps/viewer/src/components/owl-icon.tsx` | 两 SPA 导航品牌位 |

/owl-flat 与 owl-icon 内的 IKB、墨、纸、奶油 hex 是品牌资产允许值,纳入机检 allowlist。
