# Plugin mechanism

Design authority: `docs/design/11-extension-plugins.md`. This note is for
authoring agents only; it does not own new contract.

## Registry

- First-party contrib bootstraps in Core: `acp`, `openai-http`, `mock` + default multi handlers.
- External `bora plugin install` joins the same table. Recognition = first-party ∪ installed `provide(executor)`.
- `profiles.executor: <plugin_id>` is sugar for the executor provide only. It does **not** enable bake / trajectory / other `on:` slots.
- `extensions:` is the opt-in list (`- plugin: nooa`, or `slots: [...]`, or `{slot, plugin}`). Installed-but-unlisted plugins stay off MULTI chains and off the image.
- Local path install and `bora run` use the short `plugin.yaml` id. Hub publish/install uses `org/name`.
- Resolve: explicit binding > lower priority wins; a tie with no explicit pick fail-closes.
- `bora lock` writes the resolved graph as `extension_bindings` (plugin_id / slot / source / priority / digest).

Do not revive the deleted `bora.agent_executors` entry-point bypass.

## Slot layers (L0–L5)

Ids live in `src/bora/plugins/slots.py`. Summary:

| Layer | Representative slots | Who emits |
| --- | --- | --- |
| L0 | `before/after_prepare\|run\|evaluate\|cleanup` | `application/extension_hooks` (merge **all** profile chains, not `profiles[0]`) |
| L1 | `image_contribute`, `home_overlay`, `env_*`, `env_action` | bake; cred → HOME copy; env prepare/teardown + action |
| L2 | `executor`, agent open/invoke/close, `normalize_agent_result` | `ParentAgentService`. L1: Core `TargetPlacement` + SPI `bind_to_target` |
| L3 | `evaluation_input_contribute`, `evaluation_runtime`, `score_postprocess` | around evaluator (fail-closed; must not pick PASS) |
| L4 | `trajectory_collect\|enrich\|seal`, `evidence_extra` | seal. collect/enrich are **fail-open** |
| L5 | `cleanup_actions`, `cleanup_report` | cleanup |

A public slot must have a production emit, or design / ARCHITECTURE must mark it non-public. No silent dead SPI.

Agent emit chain:

```text
open_session → pin graph → before/after_agent_open
invoke       → before_agent_invoke → executor.invoke → after_agent_invoke
             → normalize_agent_result
             → seal: trajectory_collect → enrich → Core writes trajectory.jsonl
                    → trajectory_seal → evidence_extra
close        → before_agent_close → executor.close → after_agent_close
```

## Coexists with ACP

The default coding-agent inlet remains first-party `executor: acp` + `- plugin: acp` / `options.entry`.
An external plugin is an optional mechanism. The **same harness** switches via
profiles. ACP is not the trajectory schema authority.

## Priority convention

`DEFAULT_PRIORITY = 1000`. **Lower number runs first (multi) / wins first (provide).**
First-party ACP is about `100`; the nooa example uses `110`. Explicit profile
binding beats the number.
