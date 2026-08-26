# 13 — Web UI 令牌与不变量

适用面:ageval website(landing + docs)、apps/hub、apps/viewer 三个 web 表面的**风格一致性**。
权威顺序:本文件 → 各端令牌定义文件 → 业务代码(只允许引用语义令牌)。
机检:`python3 scripts/check_design_tokens.py`(CI job `design-tokens`),文档表格与脚本内置值**互相校验**,改值必须两侧同步。

## 色彩令牌

品牌强调色仍是 International Klein Blue(IKB)双阶;中性色为冷灰(cool paper / cool ink)。
功能色可以另有**命名令牌**(error / warning / star 金等),不把界面锁成只有墨、纸、蓝。
所有值为 hex,比较大小写不敏感。业务代码仍只写语义令牌名,hex 留在令牌文件。

| 令牌 | 浅色 | 深色 | 用途 | hub/viewer(`--viewer-*`) | docs(`--color-fd-*`) |
| --- | --- | --- | --- | --- | --- |
| canvas | `#F4F5F8` | `#11141C` | 页面底色 | `canvas` | `background` |
| canvas-soft | `#EEEFF4` | `#161A24` | 卡片 / 悬浮面 / 行 hover | `canvas-soft`、`row-hover` | `muted`(`fd-card` 为本地近似) |
| canvas-soft-2 | `#E4E7F0` | `#222738` | 强填充 / 次级底 | `canvas-soft-2` | `secondary` |
| hairline | `#D5D8E2` | `#2A2F3E` | 分隔线 / ring | `hairline` | `border` |
| ink | `#14161F` | `#EEF0F6` | 标题 / 强文字 | `ink` | `foreground` |
| body | `#4A4E5C` | `#9AA0B4` | 正文 | `body` | `muted-foreground` |
| mute | `#5E6376` | `#8A90A4` | 次要文字 / 图标 | `mute` | — |
| link | `#1B54E8` | `#5B7BFF` | 链接 / 主色 / 焦点(IKB) | `link` | `primary`、`ring` |
| link-deep | `#001F73` | `#8AA0FF` | hover(浅色加深 / 深色提亮) | `link-deep` | — |
| error | `#D40000` | `#FF5C5C` | 错误 | `error` | — |
| error-soft | `#F7D4D6` | `#3B1414` | 错误次底(toast 等实色洗底,非透明) | `error-soft` | — |
| warning | `#F5A623` | `#F5A623` | 警告 | `warning` | — |
| warning-soft | `#F4ECDE` | `#3A2E1D` | 警告次底 | `warning-soft` | — |
| link-soft | `#DAE2F6` | `#1E2645` | IKB 次底(成功 / tip toast) | `link-soft` | — |
| star | `#E3B341` | `#F5C84C` | Star 填实金 | `star` | — |
| code-bg | `#F4F5F8` | `#0C0E14` | 代码底 | `code-bg` | — |
| accent(landing) | `#5B7BFF`(亮)/ `#002FA7`(深) | 同左 | landing `--accent` / `--accent-deep` | — | — |

landing 的 oklch 系(`oklch(15.4% 0.018 264)` 底等)是本表的 oklch 等值表达,视为同一令牌;
`shell-*` 语法高亮色为 viewer 本地扩展,不跨面。

## 字体

| 角色 | 栈 | 说明 |
| --- | --- | --- |
| sans | `Geist` → `Inter` → `system-ui` → CJK(`Noto Sans SC` / `PingFang SC` / `Microsoft YaHei`) | 全部界面正文;hub/viewer 为系统栈(Geist 命中本地),website 经 next/font 加载 |
| mono | `Geist Mono` → `ui-monospace` → `Menlo` | 代码块 / 命令条 / 数字对齐（`tabular-nums`）；列表与表格里的非数字可读字段用 sans |
| display | `Anton`(wordmark 专用) | 只用于品牌瞬间(hero、logo),**永不**进正文或工具 UI |

## 形状与动效

- **圆角**:6 / 8 / 12px 三档(sm 控件、md 默认、lg 卡片);不发明新档,hero 面板上限 16px。
  按钮走 6px,不要 `clip-path` 切角。
- **动效**:默认 `--ease-smooth` `cubic-bezier(0.22, 1, 0.36, 1)`、200ms。
  Hub / Viewer 只允许 CSS(无 GSAP / Motion)。Landing 允许一次性 hero stagger 与 8px view-timeline 揭示,进场可到 400ms(强调瞬间,须在 `website/DESIGN.md` 写明)。
  Landing 像素标(`OwlPixelMark`)是第三条 landing 例外:canvas 2D 把 owl 面标栅格成方块,hero 一次性 assemble(约 1.4s);指针在 hero 内时方块径向推开;assemble 完成后整标共用一条透明度呼吸(6s,最暗 35%,最亮 80%),并带轻微整体起伏/旋转与边缘 drift。不是磁吸或光标拖尾。`prefers-reduced-motion` 为静止像素标。导航 logo 仍用静态 SVG。
  Landing hero 背景允许 ThreeUI `signal-particles` 点阵场(本地 canvas,不走其 iframe;`speed` 为原 `time += 0.02` 的倍率)。只铺在 hero,`pointer-events: none`,`prefers-reduced-motion` 不挂载。
  第二档命名曲线是已记录例外,不得再发明 playground 弹簧:
  - `--ease-spring` `cubic-bezier(0.34, 1.56, 0.64, 1)`:toast 进场(可到 550ms)、star burst 回弹、按钮松开回弹(可到 500ms)
  - `--ease-glide` `cubic-bezier(0.65, 0, 0.35, 1)`:PillTabs 指示条(250ms)
  按下 `--t-press` 80ms `ease-out`(Squish Button)。Tooltip 等待 80ms 是意图延迟,不是位移时长。关闭可以快于打开。
  允许的语汇:UnderlineTabs 滑条、PillTabs(文件树 Local / Shared / Overlays)、Toast Overshoot(底中)、Like Burst(仅 plugin/agent star;粒子最多 8 颗,色走 `star` 令牌)、Floating Label(描述填写框)、Squish Button、`data-ageval-pop` 弹层、`data-ageval-menu` 下拉。
  禁止:磁吸、光标拖尾、3D tilt、自定义光标、无限漂浮/旋转/脉冲、滚动钉住、横向 hijack。
  `prefers-reduced-motion: reduce` 必须落到最终态(toast 仍出现但不位移;burst 无粒子;按钮不缩放)。
- **焦点**:IKB 是唯一焦点色。按钮 / 链接用 `ring-2 ring-link/70`(landing 3px outline);
  输入框 / select / textarea 只把描边换成 1px `border-link`,不叠 ring。
- **选区**:`::selection` 用 IKB 28% 透明底(三端统一)。
- **深度**:弹层阴影用 `--viewer-shadow-pop` 令牌(hub/viewer);禁硬投影。
  `backdrop-blur` 至多两档(sticky header 用薄档)。

## 组件语汇(应用层)

| 语汇 | 规则 |
| --- | --- |
| 主按钮(SPA Button `default`) | IKB 填充 + `rounded-[6px]` + `font-mono text-[13px] font-semibold` + `focus-visible:ring-2 ring-link/70`,hover `link-deep`。`:active` 为 Squish(`scale` 约 0.94、80ms 按下 / spring 松开) |
| 下划线 tab | `UnderlineTabs`:sans `text-sm font-medium` + 滑动 IKB 条(`transform`/`width` 200ms)。不要再复制 `border-b-2` 手写条 |
| 分段 pill | `PillTabs`:测量目标宽后 glide 指示条。文件树 Local / Shared / Overlays 与同类分段切换用这个,不要手写 `bg-canvas-soft` 硬切 |
| Toast | 底中 Overshoot 进场;只用于没有本地成功态的写操作。Copy / star 等控件自身已有反馈的不要再 toast。实色 `*-soft` 次底 + `--viewer-shadow-pop`,无描边、无第三方面包。图标走对应功能色,正文走 `body` |
| Select / 下拉 | `Select` / `DropdownMenu` 用 `data-ageval-menu` 进场(220ms smooth, 随 `data-side` 上下),触发器 chevron 旋转 + squish;选项 `data-highlighted` 色过渡,选中勾 `ease-spring` pop |
| Floating Label | 描述填写框(plugin / org 等):placeholder 在 focus 或有值时抬成 label;焦点色走 `link` |
| Catalog 卡 | plugin / agent 市场包用 `CatalogCard`:12px 圆角、hairline、hover `canvas-soft`。标题为 20px 实体标 + `org/name`(+ official)。**first-party contrib overlay** 走短 id（无 `org/` 前缀）；左侧用侧栏 GitHub 链同一地址（默认 `https://github.com/ZJU-REAL/ageval`）的 GitHub 头像（`BrandMark`），名称右侧 lucide `HousePlug` 走 `link`（IKB，不复用 OfficialMark / BadgeCheck）。描述固定两行高。卡上不画 slot/binding tag。底行同一排：左侧 `download_count` 与 star 数（lucide `Download` / `Star` + 数字，卡上不可点 star），右侧更新日期。无 `created_at` 就不要画日期。Star 操作只在详情页头右侧无描边 icon;填实用 `star` 金。Datasets / jobs / leaderboard / members 用表 |
| 页头(PageHead) | h1 + 可选 sub + hairline(无编号 kicker) |
| 相位/耗时图谱 | `--viewer-phase-1..6` 用 ink / body / mute / hairline 冷灰阶。执行段 `--viewer-phase-1` 为 ink 与 mute 的 `color-mix`（约 55% ink），不用实心 ink，也不用 IKB。IKB 留给链接 / 焦点 / 主 CTA。禁 zinc 等外部灰阶 |
| 弹层(tooltip/select/dropdown/dialog) | hairline 边框 + `--viewer-shadow-pop` |
| 危险确认 | Modal：较大标题 + mute 说明后果 + Cancel / Confirm 两枚按钮 |

## 不变量(十条)

1. 色值只允许出现在令牌定义文件与品牌资产(owl 组件);业务代码只写语义令牌名。
2. IKB 仍是链接 / 焦点 / 主 CTA / 品牌位,禁大面积底色(landing ink-banner 例外)。error / warning / star 等功能色走各自令牌,不挤进 IKB,也不要求界面只有墨纸蓝。
3. 中性色三层语义:`canvas*` 是面、`hairline` 是线、`ink/body/mute` 是字;`mute` 永不做正文。
4. `Anton` 只做 wordmark;正文一律 sans 栈 + CJK 回退;中文标题粗细上限 semibold。
5. 主 CTA 用 6px 圆角 + IKB 填充;表格 / 输入 / 普通控件用同一套圆角三档。不要切角 `clip-path`。
6. 焦点可见性不妥协。字段用 1px IKB 描边;其它控件用 2px IKB 环
   (landing 3px outline)。
7. 选区、hover、active 的色彩表达一律引用令牌,不自调 hex / opacity 组合。
8. 动效默认 `--ease-smooth` 200ms。`--ease-spring` / `--ease-glide`、按下 80ms、toast 550ms、landing hero/章节揭示 400ms 是已记录的例外。其它曲线或时长先改本文件。
9. 图标三用途:产品品牌用 owl 系列(`owl-flat.tsx` / `OwlIcon`);功能用 lucide;plugin/agent 实体标默认 GitHub 头像(`uploaded_by`),可改闭包彩色标或另一个 GitHub login。闭包 SVG/PNG 在 `apps/hub/src/lib/brand-marks/assets/`,彩色,不把第三方 logo 组件库当运行时依赖。文件树仍用 `material-icon-theme`(既有例外)。
10. 深度感不用硬投影;blur 分档封顶,不为单个组件发明新档。

## 品牌资产入口

| 资产 | 位置 | 用途 |
| --- | --- | --- |
| `OwlFlatMark` / `Icon` / `Peek` / `Plate` / `Lockup` / `Watermark` | `website/src/components/owl-flat.tsx` | landing 水印、导航、docs lockup、备用底板。字形是面标(Figma cubic),不是全身立姿 |
| `OwlIcon`(面标) | `apps/hub/src/components/owl-icon.tsx`、`apps/viewer/src/components/owl-icon.tsx` | 两 SPA 导航品牌位。与 website `OwlFlatIcon` 同一 path |
| favicon | `website/src/app/favicon.ico` + `website/public/favicon.svg`；`apps/{hub,viewer}/public/favicon.{ico,svg}` | 黑方底板 + 白面标。只用 ico（浏览器默认 `/favicon.ico`）和 svg，不另备 png |
| 实体/机制标 | `apps/hub/src/lib/brand-marks/` | plugin / agent 卡片与详情、Leaderboard。默认 uploader GitHub 头像;闭包为彩色真实标。ink 标固定白底，paper 标固定黑底 |

`owl-flat` 与 `owl-icon` 内的 IKB、墨、纸、奶油 hex 是品牌资产允许值,纳入机检 allowlist。闭包标 hex 只许出现在 `brand-marks/assets/`(svg/png),不进 ts/tsx。
`OwlFlatPlate` 四色:`paper` / `cream`(深底浅标)、`ink`(浅底深标)、`klein`(IKB `#1B54E8` 底 + 白标)。导航图标走 `currentColor`。
