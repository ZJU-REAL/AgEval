# agent-skills

`ageval.plugin/1` that expands Dataset skill folders and instruction files
into the dests each bound ACP entry actually reads. Copy stays in
`home-files`. Registers `on: home_overlay` only. No bake.

Default landing zone is each actor's Attempt `$HOME`. Workspace is opt-in
for skills (`dest_roots`). Workspace-root `AGENTS.md` is always written
when an `instructions` row is present.

## Install

```bash
uv run ageval plugin install plugins/agent-skills
```

That also installs sibling `plugins/home-files` when the cache is empty.
Install writes `$AGEVAL_HOME/plugins` only. It never rewrites profiles and
never inserts `home-files` into `extensions[]`.

## Bind

```yaml
executor: acp
extensions:
  - plugin: acp
    options:
      entry: grok-build
  - plugin: agent-skills
    options:
      dest_roots: [home, workspace]
      skills:
        - src: overlays/skills/jsonl-agg
      instructions:
        - src: overlays/AGENTS.md
```

| Field | Rule |
| --- | --- |
| `src` | Relative to the overlay root: the installed Agent package when the binding has `agent_ref`, otherwise the Dataset root. No `..`, no absolute path, no host `~`. |
| `dest` | Not author-written. Dest comes from the entry table. |
| `skills[]` | One folder per row. Folder must contain `SKILL.md`. Folder name is the skill name. |
| `instructions[]` | `AGENTS.md` and (when `claude-code` is bound) `CLAUDE.md`. |
| `dest_roots` | Default `[home]`. Authors may add `workspace`. |

Skills copy `<src>` → `<root>/<prefix>/<skill-name>/`. Dests are deduped.

| entry | HOME prefix (default) | workspace prefix (opt-in) |
| --- | --- | --- |
| always | `.agents/skills/` | `.agents/skills/` |
| `codex` | `.codex/skills/` | `.codex/skills/` |
| `claude-code` | `.claude/skills/` | `.claude/skills/` |
| `opencode` | `.config/opencode/skills/` | `.opencode/skills/` |
| `pi` | `.pi/agent/skills/` | `.pi/skills/` |
| `grok-build` | generic `.agents` only | generic `.agents` only |

Instruction files (same bytes as each `instructions[]` src):

| file | when | HOME | workspace |
| --- | --- | --- | --- |
| `AGENTS.md` | any `instructions` row | `.codex/AGENTS.md` if lock has `codex` | always workspace root `AGENTS.md` |
| `CLAUDE.md` | lock has `claude-code` | `.claude/CLAUDE.md` | workspace root `CLAUDE.md` |

Do not drop `AGENTS.md` at `$HOME/AGENTS.md`. Engines do not look there.

To publish the same skill / instruction files on Hub Agent appearances, list
them on this role as `overlays:` (for example `overlays/skills/jsonl-agg` and
`overlays/AGENTS.md`). Core does not infer that list from `src`.

## Run

```bash
uv run ageval plugin install plugins/agent-skills
uv run ageval lock examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.grok-build.agent-skills.yaml
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.grok-build.agent-skills.yaml
```
