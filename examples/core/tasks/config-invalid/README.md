# config-invalid

**Expected-failure** package for Config validation.

`parameters.models.default` points at a profile id that does not exist
(`does-not-exist`). Lock must fail closed with a clear error — never partially
succeed.

## What you learn

- Invalid packages fail at **lock**, not at run
- Error surface: exit **2**, `error_code` ≈ `unknown_profile`
- Harness / evaluator entrypoints are placeholders and must never execute

## Run

```bash
uv run bora lock examples/core --task config-invalid
```

Expect **non-zero** exit (typically 2). A successful lock is a regression.
