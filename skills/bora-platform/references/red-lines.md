# Red lines (worked examples)

## Trajectory ≠ PASS

- **OK:** Agent invoke fails; Result status ERROR/FAIL; trajectory dirs still present.
- **Forbidden:** Infer PASS because `final-response.json` exists or harness returned `completed`.

`HarnessTerminal.completed` ≠ PASS. Evaluator is independent.

## Secrets

- **OK:** `agent_profiles` with executor kind + model id only; credentials via host env locators.
- **Forbidden:** API keys, DSN passwords, Bearer tokens in `bora.yaml`, lock JSON, evidence files, skill text, or examples committed to git.

## Adapter naming

- **OK:** `codex`, `pi`, `opencode`, `openai-http`, `postgresql`, docker provider.
- **Forbidden:** `TerminalBenchAdapter`, task-id branches, domain names as production adapter modules.

## Evidence grade inflation

- **OK:** Document `execution_location: parent-api-client` when Agent runs on parent under Docker Attempt.
- **Forbidden:** Claim full `isolated` because harness container passed once.
