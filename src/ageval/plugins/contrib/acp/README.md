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

## Capabilities

| | Value |
| --- | --- |
| export | exclusive `executor` |
| inject | `environment`: `attach_stdio` |
| chain | `after_environment_ready` (probe the box; install the entry only if missing — official images already bake pi / Codex / Claude + adapters), `trajectory_collect` |
| bake | — (official Attempt image; invoke does not `npm i`) |

Missing `attach_stdio` fails at **lock**, not mid-invoke.

## Parameters

`options` merge: profile `options` then this plugin's `extensions` row (last wins).

| Name | Default | Purpose |
| --- | --- | --- |
| `options.entry` | *(required)* | ACP entry id. Shipped: `codex`, `claude-code`, `pi`, `opencode`, `grok-build`. Missing → lock `acp_entry_required`. |
| `options.reasoning_effort` | unset | Applied when the entry advertises a reasoning selector. Omit to keep the entry default. |
| `model` | `entry-default` | Session model id. Binding is entry-specific (`config-option` vs entry-default-only). |
| `api_key` | unset | Env **locator name** projected into the attach env. Value never enters the lock. |
| `base_url` | unset | Projected into the attach env when the entry uses an OpenAI-compatible base. |

Rejected on `options` (entry-registry truth; fail closed): `command`, `args`, `detect_command`, `install_command`, `version`, `acp_command`, `engine_command`, `acp_version`, `credential_env_names`.

Python ACP SDK stays on the parent. It does not go into the Attempt image.

Pi: official registry `pi-acp` (`pi --mode rpc`). Do not confuse it with
the reverse bridge `pi-shell-acp`.

Not a Hub install. `ageval plugin install acp` fail-closes: the id is
reserved.
