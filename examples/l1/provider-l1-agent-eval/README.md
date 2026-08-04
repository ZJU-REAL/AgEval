# provider-l1-agent-eval

Positive **Docker L1** smoke: isolated Attempt + real Agent + clean evaluator PASS.

Same business contract as `core/agent-eval` (`answer == 42`), but
`provider.kind: docker` with `assurance: l1`. Proves the L1 worker path can still
deliver a truthful independent PASS.

## What you learn

- L1 is an isolation / assurance mode, not a different scoring model
- Agent result is projected into the container workspace for the harness
- Evaluator runs clean of hidden material

## Requirements

- Docker available
- Codex (or configured executor) reachable for the profile
- Platform in `bora.yaml` may need adjusting for your machine (`linux/arm64` default)

## Run

```bash
uv run bora lock examples/l1/provider-l1-agent-eval --task provider-l1-agent-eval
uv run bora run  examples/l1/provider-l1-agent-eval --task provider-l1-agent-eval
```
