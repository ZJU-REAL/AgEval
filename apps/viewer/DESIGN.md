---
version: alpha
name: ageval-Viewer-IKB
description: >
  Local ageval dataset results viewer. Product chrome on the shared Klein Blue
  / cool-ink system (website landing + docs). Hairline tables, Geist/Inter +
  mono captions. Surface is Jobs → Tasks → Trial drill-down — not a marketing site.

colors:
  primary: "#14161f"
  on-primary: "#f4f5f8"
  ink: "#14161f"
  body: "#4a4e5c"
  mute: "#7a7f90"
  hairline: "#d5d8e2"
  hairline-strong: "#9aa0b4"
  canvas: "#f4f5f8"
  canvas-soft: "#e8eaf1"
  canvas-soft-2: "#e4e7f0"
  link: "#002FA7"
  link-deep: "#001f73"
  success: "#002FA7"
  error: "#ee0000"
  error-soft: "#f7d4d6"
  warning: "#f5a623"
  selection-bg: "#002FA7"
  selection-fg: "#14161f"
  row-hover: "#e8eaf1"

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

ageval Viewer is a **local results console** for one opened dataset (no Registry).

1. **Jobs** — suite runs under `.ageval/suite-runs/` and unclaimed single Attempts
2. **Tasks** — per-task rows inside a job summary
3. **Trial / task detail** — run meta, reward/status, copyable `ageval` command
4. **Job row menu** — action slot is note, else pin, else hover settings.
   Hover a note icon for the text. Click for Pin / Note / Delete.
   Checkboxes select rows; with a selection, the filter-row count becomes
   a bulk delete. Pin and notes live in this browser only. Delete still
   previews, then confirms; suite delete always cascades Attempts. Hub
   write stays out.

Design is **product chrome on Klein Blue / cool ink**, not a marketing hero:

- Cool paper / cool ink canvas, ink text, hairline dividers
- Accent and links use IKB `#002FA7` (light) / `#5B7BFF` (dark)
- No decorative multi-color mesh gradients in this app
- Tables + filters + breadcrumbs carry the UI
- Geist / Inter + mono for numbers and commands

## Information architecture

| Route | Content |
| --- | --- |
| `/` | Jobs table: search, filters, select, hover-reveal click menu (pin / note / delete) |
| `/jobs/:jobId` | Tasks table for that suite run (no per-Attempt delete) |
| `/jobs/:jobId/tasks/:taskId` | Trial-level detail + command strip |

Breadcrumb: `Jobs > {jobId} > {taskId}` with `>` separators; every non-current
segment is clickable.

## Visual rules

### Do
- Use hairline borders (`#d5d8e2` light / `#2a2f3e` dark) for table rows and toolbars
- Tabular numbers for Result / score / duration / trial counts
- Mono only for commands, digests, technical labels
- Primary action = ink (copy, primary buttons); links use IKB
- Error / exception text in `#ee0000`
- Row hover = soft canvas `#e8eaf1` / `#1a1e2a`
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
| `Select` / `DropdownMenu` | Harness / model / time filters |
| `Table` | Jobs, tasks, trials |
| `Button` | Copy command, ghost icon actions |
| `Breadcrumb` | Path navigation |
| `Badge` | Optional status chips (restrained) |

## Theme modes

| Mode | Behavior |
| --- | --- |
| `light` | Cool paper canvas (`#f4f5f8`), ink text, IKB links |
| `dark` | Cool ink canvas (`#11141c`), light ink, `#5B7BFF` links |
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
