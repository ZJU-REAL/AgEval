# Red lines (worked examples)

## Trajectory ≠ PASS

- **OK:** Agent invoke fails; Result status ERROR/FAIL; trajectory dirs still present.
- **Forbidden:** Infer PASS because `final-response.json` exists or harness returned `completed`.

`HarnessTerminal.completed` ≠ PASS. Evaluator is independent.

## Secrets

- **OK:** `agent_profiles` with `executor` / ACP `options.entry` / model id only; credentials via host env locators.
- **Forbidden:** API keys, DSN passwords, Bearer tokens in `bora.yaml`, lock JSON, evidence files, skill text, or examples committed to git.

## Adapter naming

- **OK:** yaml `executor: acp` + `options.entry: codex|pi|opencode|…`; `openai-http`; `postgresql`; docker provider.
- **Forbidden:** `executor: codex|pi|opencode|claude-code` as private CLI kinds (migrated); `TerminalBenchAdapter`; task-id branches; domain names as production adapter modules.

## Plugins

- **OK:** `bora plugin install plugins/nooa` then bind `executor: nooa` in profiles; L1 Ready only after `image_contribute` bake.
- **Forbidden:** Treat install as L1-ready; rewrite profiles from install; `if kind == "nooa"` in Core.

## Evidence grade inflation

- **OK:** Document `execution_location: parent-api-client` or `attempt-container` as measured.
- **Forbidden:** Claim full `isolated` because harness container passed once.
