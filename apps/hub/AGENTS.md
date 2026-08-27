# apps/hub — agent scope lock

Visual language: [`docs/design/13-web-ui-tokens.md`](../../docs/design/13-web-ui-tokens.md).
Theme constants: YAML in [`apps/viewer/DESIGN.md`](../viewer/DESIGN.md) (shared).
Which component to reuse: [DESIGN.md](./DESIGN.md). This file is product scope.

| Do | Do not |
| --- | --- |
| Browse Registry packages (Datasets) | Replace local `ageval view` Jobs IA |
| README + Files (package tree via #38) | Full Run/Attempt evidence browser (#43) |
| Task Jobs **list only** | Click-through into trial trajectory |
| Leaderboard tab (#40) | Suite-level PASS authority |
| Agent appearances on `/agents/:id` — derived via `agent_ref`; `?model=` selects a registered model | Persist a Runtime table; invent suite or per-role PASS; keep `/runtimes`; add `/agents/:id/models/:model` |
| Same stack as viewer (Vite/React/shadcn) | Second component library / marketing CSS |

Registry API is the data plane. Token stays in browser storage only.

Do not describe page layout in this file. Hub product rules stay in docs/12 and docs/14.
Taste: [DESIGN.md](./DESIGN.md) plus Viewer DESIGN.md **Taste**. Not a landing.

## UI reuse (mandatory)

Stack is Vite + React + Tailwind + **shadcn/ui** under `src/components/ui/`.
Same family as Viewer. Role → component map: [DESIGN.md](./DESIGN.md).

1. **Reuse a shipped control.** Copy an existing instance, including its
   focus classes. Version / filter / menu lists use
   `@/components/ui/select` (see `VersionSwitcher`) or
   `@/components/ui/dropdown-menu`. Catalog search uses `CatalogScopeBar`.
2. **No native chrome.** Product UI must not use raw `<select>`, `<option>`,
   or unstyled `<button>` as the visible control. Radix/shadcn owns focus,
   trigger, and list.
3. **Do not trust primitive defaults.** `Input` defaults to edit-field IKB
   focus (`border-link`). Scan chrome (search / filter / `Select` trigger)
   keeps `hairline` on focus — docs/13. A new search that "uses Input" and
   keeps the default is wrong.
4. **Operator labels, not digests.** Dropdown rows show a human label
   (`versionLabel`, `patch N`) plus a date via `SelectItem` `trailing` /
   `formatDay` / `formatDate`. `run_id`, sha256, and other identity strings
   stay in the breadcrumb / mono heading, not in the list text.
5. **Catalog cards for plugins and agents.** Marketplace packages use
   `CatalogCard` / `CatalogCardGrid`. Datasets, jobs, leaderboard, members,
   and suites stay hairline tables.
6. **Underline tabs / pills.** Section switchers use `UnderlineTabs`.
   Segmented switches use `PillTabs`. Do not add another `border-b-2`
   tab strip or hard-cut segmented fills.

New chrome requires a new `src/components/ui/` primitive first, used by both
Hub and Viewer. Do not one-off style a native element.
