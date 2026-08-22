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
| Plugins (`/plugins`, Home, org, user public) | **Catalog cards** (`CatalogCard` / `CatalogCardGrid`) | Marketplace identity: `org/name`, official mark, date, description, slot/binding tags |
| Agents (`/agents`, Home, org, user public) | **Catalog cards** | Same: one job binding is a package |
| Datasets, jobs, leaderboard, members, suites | **Hairline tables** | Dense comparable rows (sort, scan, bulk) |

### Catalog card rules

- Radius 12px, hairline border, `canvas` fill. Hover: `canvas-soft`. Focus: `ring-2 ring-link/70`.
- Motion: `200ms` / `cubic-bezier(0.22, 1, 0.36, 1)`.
- Grid: `1 / 2 / 3` columns (`grid-cols-1 sm:grid-cols-2 xl:grid-cols-3`). N packages → N cells.
- Header: `org/name` title plus official mark on the left, updated date on the right.
- Description: fixed two-line block (`h-10` / `leading-5` / `line-clamp-2`). Missing description uses `ageval.plugin/1 package` / `ageval.agent/1 package`. List rows without preview load by-digest meta.
- Tags sit at the bottom of the card (`mt-auto`). Mute counts (`download_count` + `favorite_count`) share that same row on the right (lucide `Download` / `Star` + number).
- Loading uses `CatalogCardSkeleton` (same grid, pulse). Empty states use a dashed well.

## Motion

- Duration `200ms`, easing `ease-smooth` (`cubic-bezier(0.22, 1, 0.36, 1)`). Close/dismiss can be faster than open; tooltip wait is `80ms` (intent delay, not a travel duration).
- Underline tabs (`UnderlineTabs`) slide the IKB bar with `transform` + `width`. Do not reintroduce per-page `border-b-2` tab copies.
- Modal/tooltip enter with `data-ageval-pop` / `data-ageval-scrim`. Honor `prefers-reduced-motion`.
- No GSAP or Motion on Hub. No 3D tilt, magnetic hover, or scroll hijack.
