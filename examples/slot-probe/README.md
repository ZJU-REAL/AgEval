# example/slot-probe

Database for **multi-slot extension SPI** regression.

Companion plugin: [`plugins/slot-probe`](../../plugins/slot-probe/).

| Task                                  | Assurance       | Exercises                                                 |
| ------------------------------------- | --------------- | --------------------------------------------------------- |
| [`l0-env-agent`](tasks/l0-env-agent/) | L0 + postgresql | env multi (`post_setup.sh`) + agent multi + score metrics |
| [`l1-agent`](tasks/l1-agent/)         | L1 docker       | ACP in attempt-container; parent multi hooks still emit   |

## Prerequisites

```bash
export AGEVAL_HOME="${AGEVAL_HOME:-$HOME/.ageval}"
export AGEVAL_SLOT_PROBE_DIR="${AGEVAL_SLOT_PROBE_DIR:-/tmp/ageval-slot-probe-obs}"

uv run ageval plugin install plugins/slot-probe
uv run ageval plugin install plugins/nooa   # L0 host SPI agent
```

L1 PASS needs ACP credentials (profile `probe-acp` uses `api_key: ${glm_coding_api_key}`).
Copy from another Database `.env` or set the locator env var on the host
(values never enter lock/evidence).

## Commands

```bash
uv run ageval tasks examples/slot-probe
uv run ageval lock examples/slot-probe --task l0-env-agent \
  --profiles examples/slot-probe/profiles.yaml

uv run ageval run examples/slot-probe --task l0-env-agent \
  --profiles examples/slot-probe/profiles.yaml

uv run ageval run examples/slot-probe --task l1-agent \
  --profiles examples/slot-probe/profiles.yaml
```

## How to verify plugin effects

| Signal                | Where                                                            |
| --------------------- | ---------------------------------------------------------------- |
| Hook order / presence | `$AGEVAL_SLOT_PROBE_DIR/hooks.jsonl`                               |
| Env post-setup shell  | `post_setup.ok` (task workdir during run) + handoff `post_setup` |
| Prompt rewrite        | trajectory **user** turn contains `[slot-probe]`                 |
| Trajectory enrich     | terminal `metadata.slot_probe` / `slot_probe_enrich`             |
| Extra evidence        | invocation `evidence_extra.jsonl`                                |
| Score adjacency       | `result.json` → `metrics.slot_probe == 1`                        |
| Lock graph            | `extension_bindings` chains include `plugin: slot-probe`         |

## Scope / non-claims

- Regression package for **host emit → plugin handler** (not a full product smoke suite).
- Does **not** upgrade evidence grade by itself.
- L0 agent is deterministic **nooa** + FixedAnswer; L1 is real **ACP** when credentials exist.
