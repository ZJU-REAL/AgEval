# builtin-executor-visibility-denied

L1 **negative**: harness tries to read evaluator-only gold; workspace view must hide it.

Under Docker filtered mounts, `evaluation/gold.json` must not be visible to the
harness. If the file is readable, the package treats that as a security FAIL.
Correct behavior: harness cannot see gold → probe records `seen_gold: false` →
evaluator PASSes the isolation property.

## What you learn

- Gold / evaluator inputs are **not mounted** into the agent/harness view
- Isolation is enforced by Provider projection, not “delete fields from yaml”
- Visibility denial is a first-class acceptance, not an accident

## Requirements

- Docker L1 path

## Run

```bash
uv run bora lock examples/l1/builtin-executor-visibility-denied --task builtin-executor-visibility-denied
uv run bora run  examples/l1/builtin-executor-visibility-denied --task builtin-executor-visibility-denied
```
