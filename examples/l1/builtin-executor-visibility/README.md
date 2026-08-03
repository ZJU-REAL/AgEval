# builtin-executor-visibility

L1 positive path focused on **visibility / Result fields** (Spec 14).

Runs an agent-eval-style Docker Attempt and expects PASS with L1 assurance
signals (e.g. `execution_location`, `assurance:l1` on Result). Semantic answer
contract remains `answer == 42`.

## What you learn

- Successful L1 runs expose honest location / assurance metadata
- Builtin executor + Docker provider composition is measurable, not assumed

## Requirements

- Docker + Codex (or configured executor)
- Same platform caveats as other `l1/` packages

## Run

```bash
uv run bora lock examples/l1/builtin-executor-visibility --task builtin-executor-visibility
uv run bora run  examples/l1/builtin-executor-visibility --task builtin-executor-visibility
```
