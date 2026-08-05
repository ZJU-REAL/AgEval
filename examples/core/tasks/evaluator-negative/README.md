# evaluator-negative

Negative control: **`HarnessTerminal.completed` ≠ PASS**.

Harness intentionally publishes a wrong answer (`answer: 0`) and still returns
`completed`. The independent evaluator must score **FAIL**. This package exists so
operators never treat a green harness terminal as a benchmark PASS.

## What you learn

- Runtime / harness outcome and evaluation verdict are separate facts
- Only the evaluator barrier may form PASS/FAIL on business truth
- Trajectory or “completed” status must not invent PASS

## Run

```bash
uv run bora run examples/core/evaluator-negative --task evaluator-negative
```

Expect overall evaluation **FAIL** (or Result status that reflects FAIL), not PASS.
