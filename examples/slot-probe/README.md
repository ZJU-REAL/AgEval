# example/slot-probe

Database for **multi-slot extension SPI** regression.

Companion plugin: [`plugins/slot-probe`](../../plugins/slot-probe/).

| Task                                  | Assurance       | Exercises                                                 |
| ------------------------------------- | --------------- | --------------------------------------------------------- |
| [`l0-env-agent`](tasks/l0-env-agent/) | L0 + postgresql | env multi (`post_setup.sh`) + agent multi + score metrics |
| [`l1-agent`](tasks/l1-agent/)         | L1 docker       | ACP in attempt-container; parent multi hooks still emit   |

## Prerequisites

```bash
export BORA_HOME="${BORA_HOME:-$HOME/.bora}"
export BORA_SLOT_PROBE_DIR="${BORA_SLOT_PROBE_DIR:-/tmp/bora-slot-probe-obs}"

uv run bora plugin install plugins/slot-probe
uv run bora plugin install plugins/nooa   # L0 host SPI agent
```

L1 PASS needs ACP credentials (profile `probe-acp` uses `api_key: ${glm_coding_api_key}`).
Copy from another Database `.env` or set the locator env var on the host
(values never enter lock/evidence).

## Commands

```bash
uv run bora tasks examples/slot-probe
uv run bora lock examples/slot-probe --task l0-env-agent \
  --profiles examples/slot-probe/profiles.yaml

uv run bora run examples/slot-probe --task l0-env-agent \
  --profiles examples/slot-probe/profiles.yaml

uv run bora run examples/slot-probe --task l1-agent \
  --profiles examples/slot-probe/profiles.yaml
```

## How to verify plugin effects

| Signal                | Where                                                            |
| --------------------- | ---------------------------------------------------------------- |
| Hook order / presence | `$BORA_SLOT_PROBE_DIR/hooks.jsonl`                               |
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
