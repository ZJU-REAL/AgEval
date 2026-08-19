# env-postgres-min

A sidecar without an orchestrator.

The task ships `environment/compose.yaml`. The box brings that project up and
joins its network, so `db:5432` is an ordinary hostname inside the Attempt.
`environment/setup.sh` probes it as the last slot of the environment phase, and
`evaluator.py` passes only if the sidecar answered.

Shipping a compose file means the task *requires* `compose`. A kind that cannot
deliver that capability fails the lock instead of starting a box it could not
finish.

## Run

```bash
ageval lock examples/journeys --task env-postgres-min
ageval run  examples/journeys --task env-postgres-min
```
