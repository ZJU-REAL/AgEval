# apps/hub — agent scope lock

| Do | Do not |
| --- | --- |
| Browse Registry packages (Datasets) | Replace local `ageval view` Jobs IA |
| README + Files (package tree via #38) | Full Run/Attempt evidence browser (#43) |
| Task Jobs **list only** | Click-through into trial trajectory |
| Leaderboard tab (#40) | Suite-level PASS authority |
| Agent appearances on `/agents/:id` — derived via `agent_ref` | Persist a Runtime table; invent suite or per-role PASS; keep `/runtimes` |
| Same stack as viewer (Vite/React/shadcn) | Second component library / marketing CSS |

Registry API is the data plane. Token stays in browser storage only.

## UI reuse (mandatory)

Stack is Vite + React + Tailwind + **shadcn/ui** under `src/components/ui/`
(`Select`, `DropdownMenu`, `Table`, `Button`, tooltip). Same family as Viewer.

1. **Reuse a shipped control.** Version / filter / menu lists use
   `@/components/ui/select` (see `VersionSwitcher`) or
   `@/components/ui/dropdown-menu`. Do not invent a parallel widget.
2. **No native chrome.** Product UI must not use raw `<select>`, `<option>`,
   or unstyled `<button>` as the visible control. Radix/shadcn owns focus,
   trigger, and list.
3. **Operator labels, not digests.** Dropdown rows show a human label
   (`versionLabel`, `patch N`) plus a date via `SelectItem` `trailing` /
   `formatDay` / `formatDate`. `run_id`, sha256, and other identity strings
   stay in the breadcrumb / mono heading, not in the list text.
4. **Copy an existing pattern.** Package versions → `VersionSwitcher`. Slot
   history on Attempt evidence → the same `Select` shape (label + trailing
   time). Jobs filters in Viewer are the same `Select` primitive.
5. **Catalog cards for plugins and agents.** Marketplace packages use
   `CatalogCard` / `CatalogCardGrid` (see `DESIGN.md`). Datasets, jobs,
   leaderboard, members, and suites stay hairline tables.

New chrome requires a new `src/components/ui/` primitive first, used by both
Hub and Viewer. Do not one-off style a native element.
