# harness-minimal

Thinnest **worker harness** smoke: no Agent, no Environment.

The harness reads `ctx.params` (`seed`, `message`), publishes a JSON artifact, and
returns `RunTerminal.completed`. Used to pin Attempt worker entry, param
projection, and publish paths.

## What you learn

- Package harness is the only business entry inside the Attempt
- `ctx.params` comes from the locked package (not a second config file)
- No Agent invoke; suitable as a fast local gate

## Run

```bash
uv run ageval lock examples/core --task harness-minimal
uv run ageval run  examples/core --task harness-minimal
```
