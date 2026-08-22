# acp-oneshot — in-box ACP client+server over `exec`

External `ageval.plugin/1`. **Not** first-party `executor: acp`.

Parent ACP is a JSON-RPC client on `environment.attach_stdio`. This plugin is
the other coding inlet: one `host.exec` per `invoke` starts the entry's ACP
server **and** a one-shot client *inside the box*. ACP frames stay in the box;
the parent learns the turn is done from process exit.

Switching pi / Claude Code / OpenCode is `options.entry` (same ids as ACP).
Do not write `executor: pi`. A box without `attach_stdio` still lock-fails
`executor: acp`; this plugin only needs `exec`.

## Install

```bash
uv run ageval plugin install plugins/acp-oneshot
```

Install updates `$AGEVAL_HOME/plugins` only — never edits package yaml.

## Bind

```yaml
format: ageval.profiles/1
environment: docker
agent_profiles:
  solver:
    executor: acp-oneshot
    model: zai-coding-cn/glm-5.2
    api_key: ${ZHIPU_API_KEY}
    options:
      entry: pi
    extensions:
      - plugin: acp-oneshot
      - plugin: docker
```

Credentials are locators projected into the **exec** env. Trajectory is not PASS.
