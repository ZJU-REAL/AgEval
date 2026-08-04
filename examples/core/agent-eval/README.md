# agent-eval

Single real **Agent invoke** + independent evaluator PASS.

Parent Agent Service runs one Codex-profile turn (prompt: return JSON
`{"answer": 42}`). The harness materializes that result as a publishable artifact;
the evaluator PASSes only when `answer == 42`.

## What you learn

- End-to-end L0 path: lock → Attempt → Agent Service → harness publish → evaluate
- Harness does not decide PASS; it only forwards agent material
- Baseline “one agent, one answer” smoke (not a full journey)

## Requirements

- Codex (or configured default executor) available on the host for the profile

## Run

```bash
uv run bora lock examples/core/agent-eval --task agent-eval
uv run bora run  examples/core/agent-eval --task agent-eval
```
