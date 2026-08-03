# provider-l1-residual-writer

L1 probe: **residual writer** must be stopped before the evaluator barrier
(`task_id: residual-writer`).

After harness work ends, nothing in the Attempt view may keep writing side
effects into evaluator inputs or shared state. Core L1 orchestration owns the
stop / barrier; package entrypoints exist so lock layout and orchestrator wiring
are real.

## What you learn

- Clean evaluator boundary: residual writers cannot poison evaluation
- Isolation is not only “hide gold” but also “stop effects before score”

## Requirements

- Docker L1 path driven by Core’s L1 orchestrator

## Run

```bash
uv run bora lock examples/l1/provider-l1-residual-writer --task residual-writer
uv run bora run  examples/l1/provider-l1-residual-writer --task residual-writer
```
