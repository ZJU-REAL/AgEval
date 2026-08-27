# ageval Hub design

**Visual constitution:** [`docs/design/13-web-ui-tokens.md`](../../docs/design/13-web-ui-tokens.md).
**SPA token listing:** YAML frontmatter in [`apps/viewer/DESIGN.md`](../viewer/DESIGN.md) (shared Hub/Viewer constants; machine-checked against docs/13). Do not fork a second palette here.
**Hub product** (Registry, listing, appearances, `?model=`): [`docs/design/12-hub-dataset-and-leaderboard.md`](../../docs/design/12-hub-dataset-and-leaderboard.md), [`docs/design/14-agent-hub.md`](../../docs/design/14-agent-hub.md).

This file does **not** inventory routes, tabs, or where a control sits on a page. It tells implementers which shipped component to reuse so a new control matches the product, not the shadcn default.

This SPA is the **Registry catalog**. It is not `apps/viewer` / `ageval view`.

Do not invent a second marketing skin or hand-rolled full-page CSS over shadcn.

## Taste

The look is already chosen. Shared anti-slop (copy, type, reject list, landing-playbook ban) is in [`apps/viewer/DESIGN.md`](../viewer/DESIGN.md) **Taste**. This section only adds Hub dials and catalog rules.

**Read:** Registry catalog for benchmark authors. Browse packages, open a dataset, scan a leaderboard. Same cool-ink chrome as Viewer, slightly less dense.

| Dial | Value | Meaning |
| --- | --- | --- |
| Variance | 3/10 | Predictable chrome. Sidebar + main column, not a marketing grid. |
| Motion | 3/10 | CSS hover / focus plus the named exceptions in docs/13. Not cinematic. |
| Density | 6/10 | Catalog cards where identity matters; hairline tables where rows compare. |

### Hub chrome

- Sidebar + top bar: opaque `canvas-soft`. Main column: `canvas`. No glass, no blur wash on the top bar.
- `nav-*` paints lucide only. Labels stay `ink` / `body`, mono 13px. Do not flood the page with those colors.
- Marketplace entities (plugin / agent) are `CatalogCard`. Comparable rows (datasets, jobs, leaderboard, members) are tables. Do not put a dataset in a card "to match plugins".
- Star on a card is a count. The write control is on the package, not the list cell.
- Search on a catalog list copies `CatalogScopeBar`.

## Reuse first

Before drawing a control:

1. Find the same job already shipped (`src/components/` or `src/components/ui/`).
2. Copy that instance — including the classes that encode focus, radius, and type.
3. If nothing exists, add a primitive under `src/components/ui/` (share with Viewer when the control is chrome). Do not one-off a native `<input>` / `<select>` / `border-b-2` tab.

`Input`'s default `focus-visible:border-link` is the **edit-field** language in docs/13. Search, filter, and other scan chrome keep `border-hairline` on focus. Copy `CatalogScopeBar`, not the primitive default.

Token values, type stacks, radii, and motion curves: the YAML in Viewer `DESIGN.md`. Focus roles and catalog-vs-table: docs/13.

## Role → component

| Role | Use |
| --- | --- |
| Page title | `PageHead` |
| Section switcher | `UnderlineTabs` |
| Segmented switch | `PillTabs` |
| Marketplace plugin / agent | `CatalogCard` / `CatalogCardGrid` |
| Catalog list (scope + search) | `CatalogScopeBar` |
| Comparable rows (datasets, jobs, leaderboard, members) | hairline `Table` |
| Version list | `VersionSwitcher` (`Select` + human label + trailing date) |
| Filter / overflow menu | `Select` / `DropdownMenu` |
| Persistable name / description | `FloatingField` / `DisplayNameEditor` / `DescriptionEditor` |
| Command | `CommandStrip` |
| Dialog / confirm | `FrameModal` / `ConfirmDialog` (portal via `OverlayRoot` / `document.body`) |
| Loading / empty | `ThinkingLogo` loading vs centered empty stack (docs/13) |

New chrome that both Hub and Viewer need starts as a `src/components/ui/` primitive, used on both sides.
