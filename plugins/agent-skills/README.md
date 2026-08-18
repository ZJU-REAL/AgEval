# agent-skills

`bora.plugin/1` that expands Database skill folders and instruction files
into the dests each bound ACP entry actually reads. Copy stays in
`home-files`. Registers `on: home_overlay` only. No bake.

Default landing zone is each actor's Attempt `$HOME`. Workspace is opt-in
for skills (`dest_roots`). Workspace-root `AGENTS.md` is always written
when an `instructions` row is present.

## Install

```bash
uv run bora plugin install plugins/agent-skills
```

That also installs sibling `plugins/home-files` when the cache is empty.
Install writes `$BORA_HOME/plugins` only. It never rewrites profiles and
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
| `src` | Relative to Database root. No `..`, no absolute path, no host `~`. |
| `dest` | Not author-written. Dest comes from the entry table. |
| `skills[]` | One folder per row. Folder must contain `SKILL.md`. Folder name is the skill name. |
| `instructions[]` | `AGENTS.md` and (when `claude-code` is bound) `CLAUDE.md`. |
| `dest_roots` | Default `[home]`. Authors may add `workspace`. |

`grok-build` uses the generic `.agents/skills/` dests only.

## Run

```bash
uv run bora plugin install plugins/agent-skills
uv run bora lock examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.grok-build.agent-skills.yaml
uv run bora run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.grok-build.agent-skills.yaml
```
