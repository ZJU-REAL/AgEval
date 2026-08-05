# config-minimal

Minimal Task Package for **Config lock only**.

Proves that `bora lock` can load, validate, and emit a deterministic lock summary
for a well-formed package. Does **not** claim a runnable Agent path or
`runnable-mvp` evidence.

## What you learn

- Valid `bora.task/1` envelope shape
- Profile reference (`parameters.models.default` → `agent_profiles`)
- Config Core does **not** import or execute `harness.py` / `evaluator.py` during lock

## Run

```bash
uv run bora lock examples/core --task config-minimal
```

Expect exit **0** and a lock summary. A full `bora run` is optional for this package
and is not the primary acceptance surface.
