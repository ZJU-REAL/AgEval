# slot-probe

`bora.plugin/1` multi-slot **observability** plugin for extension SPI regression
([Issue #71](https://github.com/ZJU-REAL/BORA/issues/71)).

Paired dataset: [`examples/slot-probe`](../../examples/slot-probe/).

## What it contributes

| Kind           | Slots                                                              | Effect (observable)                                             |
| -------------- | ------------------------------------------------------------------ | --------------------------------------------------------------- |
| **on (multi)** | `before/after_agent_open\|invoke\|close`, `normalize_agent_result` | Audit lines; prompt tag `[slot-probe]`                          |
| **on**         | `trajectory_collect`, `trajectory_enrich`, `evidence_extra`        | `trajectory.jsonl` metadata + `evidence_extra.jsonl`            |
| **on**         | `env_prepare_commands`, `env_inject`, `env_teardown_commands`      | Real `scripts/post_setup.sh` → `post_setup.ok`; handoff rewrite |
| **on**         | `evaluation_input_contribute`, `score_postprocess`                 | `metrics.slot_probe = 1` on result                              |
| **provide**    | `evaluation_runtime`                                               | Lock-visible runtime annotation                                 |
| **provide**    | `executor`                                                         | Optional echo SPI (see note below)                              |

Handlers append JSONL to **`$BORA_SLOT_PROBE_DIR/hooks.jsonl`** (default:
`./.bora_slot_probe/hooks.jsonl`). They do **real work** (subprocess, metadata
rewrite)—not declaration-DSL command rows for Core to interpret.

## Install

Install only updates `$BORA_HOME/plugins` (or `~/.bora/plugins`). **Never**
rewrites `profiles.yaml` / `bora.yaml` / `task.yaml`.

```bash
export BORA_HOME="${BORA_HOME:-$HOME/.bora}"
export BORA_SLOT_PROBE_DIR="${BORA_SLOT_PROBE_DIR:-/tmp/bora-slot-probe-obs}"
uv run bora plugin install plugins/slot-probe
uv run bora plugin list
```

## Run with the companion dataset

```bash
# L0: env + nooa FixedAnswerAgent (deterministic) + slot-probe multi hooks
uv run bora plugin install plugins/nooa
uv run bora run examples/slot-probe --task l0-env-agent \
  --profiles examples/slot-probe/profiles.yaml

# L1: docker attempt + ACP (credentials required for PASS)
uv run bora run examples/slot-probe --task l1-agent \
  --profiles examples/slot-probe/profiles.yaml

cat "${BORA_SLOT_PROBE_DIR}/hooks.jsonl"
```

### Why L0 uses `executor: nooa` (not `slot-probe`)

Config capability catalog still allowlists **declaration** executor kinds
(`acp` / `mock` / `nooa` / openai\*). Lock rejects unknown kinds even when an
installed plugin `provide(executor)`. The `slot-probe` package still **provides**
an echo executor for experiments, but the shipped L0 profile binds **nooa** +
package-local `lib.agents:FixedAnswerAgent` so lock/run stay green while multi
hooks prove emit.

## Anti-pattern

Do **not** treat this plugin as a template for “append `{kind: shell, argv:…}`
rows for Core to parse later.” Env prepare runs handler code under a live
`ctx` (`workdir` / `env_manager` / handoff).
