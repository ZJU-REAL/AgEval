# sdk-tool-guard-denied

Deterministic **tool policy denial** (pre-callable).

Same ToolSet setup as `sdk-tool-guard`, but `mode: denied` issues a third call
beyond `call_limit=2`. The third observation must be `status: denied` without
incrementing the side-effect counter past 2.

## What you learn

- Over-limit / disallowed calls fail closed before the tool body runs
- Denial is observable and scoreable without crashing the Attempt arbitrarily
- Pair with `sdk-tool-guard` for positive + negative policy coverage

## Run

```bash
uv run ageval lock examples/core --task sdk-tool-guard-denied
uv run ageval run  examples/core --task sdk-tool-guard-denied
```
