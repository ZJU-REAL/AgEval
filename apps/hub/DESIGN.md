# ageval Hub design

**Visual authority:** inherits [`apps/viewer/DESIGN.md`](../viewer/DESIGN.md)
(Klein Blue / cool-ink product chrome, hairline tables, tabular nums).
Token and invariant authority: [`docs/design/13-web-ui-tokens.md`](../../docs/design/13-web-ui-tokens.md).

This SPA is **Registry catalog** (Datasets → Task files / Jobs list / Leaderboard),
**not** the local Jobs → Trial evidence browser (`ageval view`).

Do not invent a second marketing skin or hand-rolled full-page CSS over shadcn.

## Catalog vs table

| Surface | UI | Why |
| --- | --- | --- |
| Plugins (`/plugins`, Home, org, user public) | **Catalog cards** (`CatalogCard` / `CatalogCardGrid`) | Marketplace identity: name, official mark, org, version, optional slot/binding chips |
| Agents (`/agents`, Home, org, user public) | **Catalog cards** | Same: one job binding is a package, not a sortable trial row |
| Datasets, jobs, leaderboard, members, suites | **Hairline tables** | Dense comparable rows (sort, scan, bulk) |

Do not render plugin or agent packages as a one-row `Table` again. Do not turn
jobs / leaderboard / members into cards.

### Catalog card rules

- Radius 12px, hairline border, `canvas` fill. Hover: `canvas-soft` + `motion-safe:-translate-y-px`. Active: `scale-[0.99]`. Focus: `ring-2 ring-link/70`.
- Motion: `200ms` / `cubic-bezier(0.22, 1, 0.36, 1)` only. No 3D tilt, glare, or IKB fill.
- Grid: `1 / 2 / 3` columns (`grid-cols-1 sm:grid-cols-2 xl:grid-cols-3`). N packages → N cells; no empty filler tiles.
- Glyphs: lucide `Puzzle` (plugin) / `Bot` (agent). No third icon set.
- Description and chips are optional (list payloads may omit `plugin_preview` / `agent_preview`). Fallback copy is the format name, not invented marketing.
- Nested org link uses `stopPropagation`; the card itself is the package `role="link"`.
