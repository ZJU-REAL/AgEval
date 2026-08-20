---
name: ageval-config-package
description: >
  Author ageval datasets (ageval.yaml + tasks/*/task.yaml, run.py/evaluator.py,
  profiles.yaml, environment kinds local|docker|e2b|ssh, limits, gold isolation).
  Triggers: ageval.yaml, task.yaml, profiles.yaml, dataset, environment kind.
  Never secrets in yaml. Never provider.kind.
---

# Config / dataset + task

Config Core is the only normative reader. Delivery unit is a **dataset** root.

```text
my-dataset/                 # CLI path (ageval.dataset/1)
├── ageval.yaml
├── profiles.yaml           # job: environment + agent_profiles
├── env.example
├── shared/lib/             # optional; import shared.lib.*
└── tasks/<task_id>/
    ├── task.yaml           # ageval.task/1 — roles + intent
    ├── run.py              # async def run(ctx)
    ├── evaluator.py
    ├── environment/        # Dockerfile, setup.sh, compose
    ├── evaluation/         # gold — not for Agent
    └── data/               # seed
```

CLI: `ageval lock|run <dataset-root> --task <id>`.

Files present are recognized. Do not re-declare `run.py` entrypoints in yaml. Do not put `executor` / `api_key` on the member task. Do not write `provider.kind` or `assurance`.

```yaml
# ageval.yaml
format: ageval.dataset/1
dataset_id: org/my-suite
version: "0.1.0"
tasks:
  root: tasks
```

```yaml
# profiles.yaml
format: ageval.profiles/1
environment: docker
agent_profiles:
  solver:
    executor: acp
    api_key: ${ZHIPU_API_KEY}
    options: { entry: pi }
    extensions:
      - plugin: acp
      - plugin: docker
```

Gold lives in `evaluation/` and is uploaded at evaluate, not before. `setup.sh` is the last environment slot.

`--profiles` swaps the job. `--agent` is mutually exclusive with `--profiles`.

Hub comparability still uses suite fingerprint / `upload-suite`. Do not add `n_attempts` to yaml.

Field catalog: [references/ageval-yaml.md](references/ageval-yaml.md). Isolation: [references/isolation.md](references/isolation.md). Conversion: [references/conversion.md](references/conversion.md).
