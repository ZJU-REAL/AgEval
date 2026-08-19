# home-files

`ageval.plugin/1` that copies overlay files into Attempt
`$HOME` or workspace. Registers `on: home_overlay` only. No bake.

## Install

```bash
uv run ageval plugin install plugins/home-files
```

Install writes `$AGEVAL_HOME/plugins` only. It never rewrites profiles.

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
| `src` | Relative to the overlay root: the installed Agent package when the binding has `agent_ref`, otherwise the Database root. No `..`, no absolute path. |
| `dest_root` | Required: `home` or `workspace`. |
| `dest` | Relative to that root. No `..`. Not under `evaluation/`. |

Secrets stay locators. Overlay JSON must not embed tokens. No JSON deep-merge.

To show the same files on Hub Agent appearances, list them on this role as
`overlays:` (paths under `overlays/`, resolved from the Agent package when
`agent_ref` is set). That field is the
published set; this plugin still copies only its own `files[].src`.

## Run

```bash
uv run ageval plugin install plugins/home-files
uv run ageval lock examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.opencode.glm-5.2.yaml
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.opencode.glm-5.2.yaml
```
