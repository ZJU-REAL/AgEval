# Plugin mechanism

Design authority: `docs/design/11-extension-plugins.md`. This note is for
authoring agents only; it does not own new contract.

## Registry

- First-party contrib: `acp`, `openai-http`, `local`, `docker`, `e2b`, `ssh`, `daytona`. No product mock executor.
- External `ageval plugin install` joins the same table.
- `profiles.executor` / `environment` pick exclusive winners. Chain slots are opt-in via `extensions`.
- `extensions:` is the opt-in list (`- plugin: nooa`, or `slots: [...]`, or `{slot, plugin}`). Installed-but-unlisted plugins stay off MULTI chains and off the image.
- Local path install and `ageval run` use the short `plugin.yaml` id. Hub publish/install uses `org/name`.
- Resolve: explicit binding > lower priority wins; a tie with no explicit pick fail-closes.
- `ageval lock` writes the resolved graph as `extension_bindings` (plugin_id / slot / source / priority / digest).

Do not revive the deleted `ageval.agent_executors` entry-point bypass.

## Slots

Ids live in `src/ageval/plugins/slots.py`. Exclusive: `environment`, `executor`, `evaluation_runtime`, `trajectory_seal`. Chain: environment ready/setup, run bookends, agent open/invoke/close, evaluate bookends, `trajectory_collect` / `trajectory_enrich`, `cleanup_report`.

`evaluation_runtime` / `trajectory_seal` have engine defaults (`plugin_id: default`). No job-field sugar; replace only with an explicit `extensions` row. PASS still enters only through `bind_evaluation`.

A public slot must have a production emit, or design / ARCHITECTURE must mark it non-public. No silent dead SPI.

Agent emit chain:

```text
open_session → pin graph → before/after_agent_open
invoke       → before_agent_invoke → executor.invoke → after_agent_invoke
             → normalize_agent_result
record       → trajectory_collect → enrich → trajectory_seal writes trajectory.jsonl
close        → before_agent_close → executor.close → after_agent_close
```

## Coexists with ACP

The default coding-agent inlet remains first-party `executor: acp` + `- plugin: acp` / `options.entry`.
An external plugin is an optional mechanism. The **same `run.py`** switches via
profiles. ACP is not the trajectory schema authority.

## Priority convention

`DEFAULT_PRIORITY = 1000`. **Lower number runs first (chain) / wins first (exclusive).**
First-party ACP is about `100`; the nooa example uses `110`. Explicit profile
binding beats the number.
