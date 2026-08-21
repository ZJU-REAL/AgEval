# ACP job bindings (LiteLLM overlay)

Same journeys harness. Bind ACP `entry` on `- plugin: acp`. Bind previously
unbound LiteLLM model ids with `- plugin: home-files` and a Database overlay
file. No Core model-prefix switch.

```bash
uv run ageval plugin install plugins/home-files
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.opencode.qwen3.8-max.yaml
```

`api_key` is the env locator `litellm_api_key`. Overlay JSON must not embed tokens.

To ship skill folders for a cwd-scanning ACP entry (generic `.agents/skills`):

```bash
uv run ageval plugin install plugins/agent-skills
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/acp-profiles/profiles.acp.grok-build.agent-skills.yaml
```
