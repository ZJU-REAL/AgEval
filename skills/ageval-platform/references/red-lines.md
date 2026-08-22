# Red lines (worked examples)

## Trajectory ≠ PASS

- **OK:** Agent invoke fails; Result status ERROR/FAIL; trajectory dirs still present.
- **Forbidden:** Infer PASS because `final-response.json` exists or `run.py` returned `completed`.

`RunTerminal.completed` ≠ PASS. Evaluator is independent.

## Secrets

- **OK:** Dataset bindings with `executor` / ACP `- plugin: acp` / `options.entry` / model id only; credentials via host env locators.
- **Forbidden:** API keys, DSN passwords, Bearer tokens in `ageval.yaml`, lock JSON, evidence files, skill text, or examples committed to git.

## Adapter naming

- **OK:** yaml `executor: acp` + `- plugin: acp` / `options.entry: codex|pi|opencode|…`; `openai-http`; docker environment winner.
- **Forbidden:** `executor: codex|pi|opencode|claude-code` as private CLI kinds; `TerminalBenchAdapter`; task-id branches.

## Plugins

- **OK:** `ageval plugin install plugins/nooa` then bind `executor: nooa` in profiles; docker Ready only after image layers bake.
- **Forbidden:** Treat install as docker-ready; rewrite profiles from install; `if kind == "nooa"` in Core; product `executor: mock`.

## Evidence grade inflation

- **OK:** Document measured `execution_location`.
- **Forbidden:** Claim full `isolated` because one docker Attempt passed once. Skip CI ACP/E2B is not a pass.

## Box kind

- **OK:** `environment: local|docker|e2b|ssh|daytona`.
- **Forbidden:** `provider.kind`, `assurance: l0/l1`, calling cloud sandboxes L2.
