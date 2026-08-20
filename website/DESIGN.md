# ageval Website Design System

本文档是 `website/` 的视觉与交互规范。

**色板策略：** 全站统一为 PPT / landing 的克莱因蓝（IKB `#002FA7`，暗底提亮 `#5B7BFF`）+ 冷墨中性色。文档站与 landing 共用同一套色相，不再使用暖棕 canvas。

## 设计方向

### 产品气质

- 面向 benchmark 作者、研究工程师和 Agent infrastructure 团队。
- **Landing** 使用深色冷墨 + Anton 字标 + Geist / Noto Sans SC + 切角按钮。
- **文档阅读层** 使用同一套克莱因蓝与冷墨中性色；标题与正文都走 Geist / Noto Sans SC，不再用衬线。
- 装饰服从信息，不使用生成插画、拟真场景图或无语义的发光背景。

### 设计参数

| 参数 | 值 | 含义 |
| --- | --- | --- |
| Design variance | 5/10 | 允许非对称构图，保持工程秩序 |
| Motion intensity | 2/10 | 只呈现状态变化和直接反馈 |
| Visual density | 4/10 | 技术信息清晰，保留足够留白 |

## 颜色

### 核心色板

| Token | Light | Dark | 用途 |
| --- | --- | --- | --- |
| `canvas` | `#f4f5f8` | `#11141c` | 页面底（冷纸 / 冷墨） |
| `canvas-soft` | `#e8eaf1` | `#1a1e2a` | 次级面、表头 |
| `ink` | `#14161f` | `#eef0f6` | 主文字 |
| `body` | `#4a4e5c` | `#9aa0b4` | 正文与说明 |
| `hairline` | `#d5d8e2` | 冷白 12% | 1px 边界 |
| `accent` | `#002FA7` | `#5B7BFF` | 链接、焦点、主按钮（克莱因蓝） |
| `accent-deep` | `#001f73` | `#8aa0ff` | hover / active |
| `dark`（landing 底） | `#11141c` | `#0c0e14` | landing 深色面 |

参考：IKB / Klein Blue 主题（#002FA7 / #5B7BFF）；viewer / hub 的冷灰 ink 仅作对比，不把 viewer link 蓝搬进本站。

### 使用规则

- 一个视口内最多出现一个主 CTA；主 CTA 用 accent 实底，链接与路径强调用同一套克莱因蓝。
- 中性色保持冷相，不要回暖棕。
- 浅色卡片用 hairline 与表面色差建层级，少用重阴影。
- 深色技术区可用极轻的蓝色径向光带作路径提示，不使用多色 AI 渐变。

## 字体

### 字体职责

- Landing 字标使用 `Anton`。文档标题与正文使用 `Geist Sans`，中文由 `Noto Sans SC` 补全。
- 技术标签、按钮、状态和字段名使用 `Geist Mono`。
- 文档导航、sidebar、TOC、搜索和交互控件使用 `Geist Sans`。
- 标题使用 sentence case；mono 标签可以 uppercase。
- 正文不能使用 monospace。不使用衬线作为文档标题。

### 字号层级

| Token | Desktop | Mobile | 用途 |
| --- | --- | --- | --- |
| Display XXL | `64px/1.08` | `42px/1.08` | 首屏标题 |
| Display XL | `40px/1.16` | `32px/1.18` | Section 标题 |
| Display LG | `28px/1.2` | `24px/1.24` | 卡片或演示标题 |
| Body LG | `18px/1.5` | `17px/1.5` | Lead paragraph |
| Body MD | `16px/1.55` | `16px/1.55` | 正文 |
| Mono label | `11px/1.4` | `11px/1.4` | eyebrow、字段与状态 |

首屏标题桌面最多两行，正文最多四行。Anton 只用于 landing 字标，不能扩散到文档正文和交互控件。

### 文档阅读层

- Fumadocs 的页面标题和正文 H1-H4 使用 Geist / Noto Sans SC，字重 700；颜色跟正文 ink（浅色近黑、深色近白），不用克莱因蓝。
- 文档正文、导航、sidebar、TOC、搜索、面包屑和分页保持 Geist Sans。
- code、pre、kbd、字段名和配置示例使用 Geist Mono。
- Fumadocs semantic token 与 landing 共用冷墨半透明原则，light / dark 均禁止纯黑、纯白或完全不透明的近黑/近白大色块。
- 搜索、popover 和菜单使用接近实色的稳定 surface，确保叠加在正文上时仍有清晰边界和可读性。

## 布局

### 页面节奏

- 内容最大宽度为 `1280px`。
- 桌面 gutter 为 `32px`，移动端为 `16px`。
- Section 垂直间距为 `80px`，移动端降为 `56px`。
- 首屏使用左右分栏：价值主张在左，真实产品演示在右。
- 深色和浅色 section 交替；颜色带负责分区，不用大阴影制造层级。

### 圆角与边界

- 默认圆角为 `4px`。
- 大型演示容器最多使用 `8px`。
- 只允许圆形 icon button 使用全圆角。
- 按钮、卡片、节点和表格统一使用 1px hairline。

## 产品演示

### 架构路径

- Landing 使用只读、可选择的阶段节点展示 Task 编译、Harness 执行、评估与证据三条架构路径。
- 每条路径保持线性阅读顺序，只解释当前接受的编译、执行和评估边界。
- 节点聚焦或点击后展示职责、输入和输出；状态由文字与视觉样式共同表达。
- 移动端保持可横向阅读的完整节点，不压缩技术标签。

### 执行生命周期

- 生命周期使用左侧阶段矩阵和右侧三节点流程图，避免只展示稀疏表格。
- 默认选中第一阶段；pointer hover、点击与键盘 focus 使用同一选中状态。
- 阶段切换只交叉淡入流程内容，不移动表格、流程节点或容器。

### 其他视觉内容

- 优先使用配置片段、运行状态、事件表、审计工件和结果摘要。
- 不使用 AI 生成图片作为产品能力解释。
- 不使用装饰性悬浮节点、视差背景或与滚动位置绑定的元素位移。

## 动效

### 允许

- `160-240ms` 的颜色、边框和背景过渡。
- tab、inspector 和 disclosure 的内容切换。

### 禁止

- 视差滚动。
- 无限漂浮、无限旋转和无限脉冲。
- hover 位移、缩放或磁吸。
- 长距离 scroll reveal。
- 多段 sticky 叙事；全站只保留导航栏 sticky。

所有动效必须支持 `prefers-reduced-motion: reduce`，此模式下直接显示最终状态。

## 组件规范

### 按钮

- 高度最少 `44px`，圆角 `4px`。
- Label 使用 Geist Mono，保持短且不换行。
- hover 仅改变背景、边框或文字色。
- focus-visible 使用 3px 半透明 accent ring。

### 卡片与数据区

- Light surface 使用半透明暖灰 canvas、hairline，不使用投影。
- Dark surface 使用 `canvas-dark` 与 `hairline-dark`。
- 技术字段采用 `label / value` 结构，label 使用 mono uppercase。
- 状态颜色必须同时配合文字，不能只依赖颜色传递信息。

### 链接与 CTA

- Hero 允许一个 primary CTA 和一个 secondary CTA。
- 相同意图在页面中保持同一文案。
- CTA hover 不移动；active 只改变填充或 inset border。

## 响应式与无障碍

- 断点使用 `768px` 和 `1024px` 作为主要布局转换点。
- 所有交互目标最少 `44 × 44px`。
- 桌面双栏在 `< 1024px` 时改为单栏。
- 图表、tab 和 inspector 必须支持键盘操作和可见 focus ring。
- 正文、按钮和状态文字至少满足 WCAG AA 对比度。
- 页面在 JavaScript 失效时仍需保留标题、正文和文档入口。

## 发布前检查

- 首屏标题、说明和 CTA 在初始视口内完整可见。
- 页面没有视差、漂浮节点和 hover 位移。
- 每个 section 都有明确的信息目标，布局类型不机械重复。
- 架构路径在桌面和移动端均无文字裁切，节点信息可键盘访问。
- 中英文文案长度均通过真实视口验证。
- `prefers-reduced-motion`、light theme 和 dark theme 均通过检查。
