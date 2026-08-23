# acp executor

First-party exclusive-slot winner for `executor: acp`.

Parent is the **only** ACP JSON-RPC client. The coding-agent Target inlet is:

```yaml
executor: acp
options:
  entry: pi   # or codex / claude / another baked entry
```

Vendor private formats are translated **outside** ageval (Mode 1 shim /
Mode 2 native / Mode 3 vendor package). Do not add a second vendor stdout
scrape in this repo.

## Slots

- exclusive `executor` — `AcpExecutor` attached to this Attempt's box
- chain `after_environment_ready` — probe the box; install the entry only
  if missing (official images already bake pi / Codex / Claude + adapters)
- chain `trajectory_collect` — tag trajectory as ACP-sourced

Inject: service `environment` with capability `attach_stdio`. Missing that
capability fails at **lock**, not mid-invoke.

Python ACP SDK stays on the parent. It does not go into the Attempt image.

Pi: official registry `pi-acp` (`pi --mode rpc`). Do not confuse it with
the reverse bridge `pi-shell-acp`.

Not a Hub install. `ageval plugin install acp` fail-closes: the id is
reserved.
