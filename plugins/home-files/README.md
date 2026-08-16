# home-files

`bora.plugin/1` that copies Database-relative overlay files into Attempt
`$HOME` or workspace. Registers `on: home_overlay` only. No bake.

## Install

```bash
uv run bora plugin install plugins/home-files
```

Install writes `$BORA_HOME/plugins` only. It never rewrites profiles.

## Bind

```yaml
executor: acp
extensions:
  - plugin: acp
    options:
      entry: opencode
  - plugin: home-files
    options:
      files:
        - src: overlays/opencode.litellm.json
          dest: .config/opencode/opencode.json
          dest_root: home
```

| Field | Rule |
| --- | --- |
| `src` | Relative to Database root. No `..`, no absolute path. |
| `dest_root` | Required: `home` or `workspace`. |
| `dest` | Relative to that root. No `..`. Not under `evaluation/`. |

Secrets stay locators. Overlay JSON must not embed tokens. No JSON deep-merge.

## Run

```bash
uv run bora plugin install plugins/home-files
uv run bora lock examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.opencode.glm-5.2.yaml
uv run bora run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.opencode.glm-5.2.yaml
```
