# acp-local-min

The smallest honest Attempt: a real coding agent, a real box, a real verdict.

`run.py` opens one Agent session and sends one instruction. The agent uses its
own tools to create `answer.txt` in the Attempt workspace. `evaluator.py` then
reads that file inside the same box and decides PASS or FAIL — the agent's own
"DONE" is never the verdict.

## What you learn

- `ctx.agent.session(...).invoke(...)` — the only Agent surface a task gets
- The box is ready before `run.py` starts: no setup, no install, no `host`
- PASS comes from `evaluator.py` reading what actually landed on disk

## Requirements

- `environment: local` in the dataset `profiles.yaml`
- An ACP entry that is installed and authenticated on this machine, named by
  `agent_profiles.solver.options.entry`. Check with `ageval executors`.

## Run

```bash
ageval lock examples/core --task acp-local-min
ageval run  examples/core --task acp-local-min
```

Exit code is `0` for PASS, `1` for FAIL, `2` for anything that stopped the
Attempt before a verdict. Evidence lands under
`examples/core/.ageval/runs/<attempt_id>/`, including `trajectory.jsonl` with
the tool call that wrote the file.
