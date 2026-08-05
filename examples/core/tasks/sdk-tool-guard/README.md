# sdk-tool-guard

Deterministic **ToolSet + CallLimit** success path (no Agent).

Harness builds a local `ToolSet` (`echo` only, `call_limit=2`), runs two allowed
calls, and publishes observations + side-effect counter. Evaluator PASSes when
exactly two successful calls ran and the counter matches.

## What you learn

- Package-local tools are guarded by SDK policy before callable body runs
- Call limits and allowlists are first-class Harness Core helpers
- No network / Agent required — fast regression

## Run

```bash
uv run bora lock examples/core --task sdk-tool-guard
uv run bora run  examples/core --task sdk-tool-guard
```
