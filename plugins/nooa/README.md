# nooa — ecosystem executor plugin

External `bora.plugin/1` package. **Not** first-party BORA core (only ACP is first-party).

## Install

```bash
BORA_HOME=/tmp/bora-demo uv run bora plugin install plugins/nooa
```

Install updates `~/.bora/plugins` (or `$BORA_HOME/plugins`) only — **never** edits
`profiles.yaml` / `bora.yaml` / `task.yaml`.

## Bind

In profiles:

```yaml
bindings:
  solver:
    executor: nooa
    options:
      agent: "lib.agents:MyAgent"
      method: "run"
```

`options.agent` is a package-local `module:Class` (or module) owned by the task
package. The plugin only loads and invokes it.

## Journeys smoke

```bash
export BORA_HOME=/tmp/bora-nooa-e2e
uv run bora plugin install plugins/nooa
uv run bora run examples/journeys --task terminal-jsonl-agg --profiles examples/journeys/profiles.nooa.yaml
```

## L1 Ready strategy

For Docker L1 tasks, nooa uses **host-in-container**: parent materializes the
host SPI and writes effects into the Attempt workspace mount. It does **not**
rely on silent host_fallback of ACP coding agents.
