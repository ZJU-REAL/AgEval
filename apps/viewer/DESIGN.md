---
version: alpha
name: BORA-Viewer-Vercel-inspired
description: >
  Local BORA Database results viewer. Visual language adapted from Vercel
  (stark ink-on-near-white, hairline tables, Geist/Inter + mono captions).
  Product surface is Jobs → Tasks → Trial drill-down — not a marketing site.
  Full upstream visual reference:
  https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/vercel/DESIGN.md
source: vercel/DESIGN.md (VoltAgent awesome-design-md), adapted for apps/viewer

colors:
  primary: "#171717"
  on-primary: "#ffffff"
  ink: "#171717"
  body: "#4d4d4d"
  mute: "#888888"
  hairline: "#ebebeb"
  hairline-strong: "#a1a1a1"
  canvas: "#ffffff"
  canvas-soft: "#fafafa"
  canvas-soft-2: "#f5f5f5"
  link: "#0070f3"
  link-deep: "#0761d1"
  success: "#0070f3"
  error: "#ee0000"
  error-soft: "#f7d4d6"
  warning: "#f5a623"
  selection-bg: "#171717"
  selection-fg: "#f2f2f2"
  row-hover: "#fafafa"

typography:
  sans: "Geist, Inter, system-ui, -apple-system, sans-serif"
  mono: "Geist Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, monospace"
  display-md:
    fontSize: 24px
    fontWeight: 600
    lineHeight: 32px
    letterSpacing: -0.96px
  display-sm:
    fontSize: 20px
    fontWeight: 600
    lineHeight: 28px
    letterSpacing: -0.6px
  body-sm:
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px
  body-sm-strong:
    fontSize: 14px
    fontWeight: 500
    lineHeight: 20px
  caption:
    fontSize: 12px
    fontWeight: 400
    lineHeight: 16px
  caption-mono:
    fontSize: 12px
    fontWeight: 400
    lineHeight: 16px
    fontFamily: mono
  code:
    fontSize: 13px
    fontWeight: 400
    lineHeight: 20px
    fontFamily: mono

rounded:
  none: 0px
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px

components:
  page-shell:
    backgroundColor: "{colors.canvas}"
    maxWidth: 1400px
    padding: "{spacing.md} {spacing.lg}"
  top-bar:
    height: 56px
    borderBottom: "1px solid {colors.hairline}"
    backgroundColor: "{colors.canvas}"
  breadcrumb:
    typography: "{typography.body-sm}"
    separator: ">"
    muteColor: "{colors.mute}"
    linkColor: "{colors.body}"
    currentColor: "{colors.ink}"
  search-input:
    height: 36px
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.sm}"
    placeholderColor: "{colors.mute}"
  filter-select:
    height: 36px
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.sm}"
    backgroundColor: "{colors.canvas-soft}"
  data-table:
    headerBackground: "{colors.canvas}"
    headerTypography: "{typography.caption}"
    headerColor: "{colors.mute}"
    bodyTypography: "{typography.body-sm}"
    bodyColor: "{colors.ink}"
    rowBorder: "{colors.hairline}"
    rowHover: "{colors.row-hover}"
    cellPadding: "10px 12px"
  command-bar:
    backgroundColor: "{colors.canvas-soft}"
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.md}"
    typography: "{typography.code}"
    linkColor: "{colors.link}"
  status-error:
    textColor: "{colors.error}"
  status-pass:
    textColor: "{colors.ink}"
  numeric:
    fontFamily: mono
    fontVariantNumeric: tabular-nums
---

## Overview

BORA Viewer is a **local read-only results console**:

1. **Jobs** — suite runs under `.bora/suite-runs/`
2. **Tasks** — per-task rows inside a job summary
3. **Trial / task detail** — run meta, reward/status, copyable `bora` command

Design is **Vercel product chrome**, not marketing hero mesh:

- Near-white canvas, ink text, hairline dividers
- No decorative multi-color mesh gradients in this app
- Tables + filters + breadcrumbs carry the UI
- Geist / Inter + mono for numbers and commands

Upstream design inventory (marketing + full tokens) lives in the source
`vercel/DESIGN.md`; this file is the **viewer-specific subset**.

## Information architecture

| Route | Content |
| --- | --- |
| `/` | Jobs table: search, column sort, filters |
| `/jobs/:jobId` | Tasks table for that suite run |
| `/jobs/:jobId/tasks/:taskId` | Trial-level detail + command strip |

Breadcrumb: `Jobs > {jobId} > {taskId}` with `>` separators; every non-current
segment is clickable.

## Visual rules

### Do
- Use hairline borders (`#ebebeb`) for table rows and toolbars
- Tabular numbers for Result / score / duration / trial counts
- Mono only for commands, digests, technical labels
- Primary action = ink `#171717` (copy, primary buttons)
- Error / exception text in `#ee0000`
- Row hover = soft canvas `#fafafa`
- Max content width ~1400px, generous but calm padding

### Don't
- Don't invent a second accent palette (no purple AI glow)
- Don't use heavy drop shadows on tables
- Don't use all-caps section eyebrows as decoration
- Don't hand-roll table / select / button primitives — use shadcn
- Don't ship dark-only or neon terminal skins as default
- Don't put em-dashes in UI copy (use hyphen)

## Components (implementation)

Prefer **shadcn/ui** (Radix + Tailwind), tokens mapped to CSS variables in
`src/index.css`:

| shadcn | Role |
| --- | --- |
| `Input` | Search boxes |
| `Select` / `DropdownMenu` | Agent / provider / model / time filters |
| `Table` | Jobs, tasks, trials |
| `Button` | Copy command, ghost icon actions |
| `Breadcrumb` | Path navigation |
| `Badge` | Optional status chips (restrained) |
| `Checkbox` | Multi-select rows (optional MVP) |
| `Separator` | Toolbar dividers |

## Theme modes

| Mode | Behavior |
| --- | --- |
| `light` | Near-white canvas, ink text |
| `dark` | Near-black canvas (`#0a0a0a`), light ink |
| `system` | Follow `prefers-color-scheme` (default) |

Toggle lives in the top-right header. Persist preference client-side.

## CLI command strip

Commands render as **shell code** on a dark code surface — not flat link-blue.
Token roles: command name, flags (`--task`), paths, strings, plain args.

## Motion

Minimal: 150–200ms opacity/background transitions on hover/focus.
No scroll hijack, no marquees, no mesh hero animations.

## Accessibility

- WCAG AA contrast on body and table text
- Keyboard: table row Enter opens detail; Escape not required but focus rings visible
- Sortable columns announce via `aria-sort`
