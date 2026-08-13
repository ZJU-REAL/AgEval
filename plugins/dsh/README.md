# dsh — DeepSeek Harness executor plugin

External `bora.plugin/1` package. **Not** first-party BORA core.

Drives [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) over
the official Python JSON-RPC SDK (`deepseek-harness-sdk` + bundled
`dsh-jsonrpc-agent`). This is **not** ACP: DSH's shipped ACP wire is too thin
for BORA evidence (no tools / reasoning / usage; model is not on
`config_options`).

```python
from deepseek_harness import DeepSeekHarness

with DeepSeekHarness(model="deepseek-v4-flash", cwd=workdir, session_root=attempt_dir) as h:
    result = h.start_session(session_id).run(prompt)
```

Profile `model` is passed on `initialize`. `api_key` is an env locator
(never a secret value). Sessions persist under the Attempt (`DSH_SESSION_ROOT`),
not the task workspace.

## Install

```bash
uv sync --extra dsh          # optional; L1 bake installs the wheels in-image
uv run bora plugin install plugins/dsh
```

Install updates `$BORA_HOME/plugins` (default `~/.bora/plugins`) only — **never**
edits `profiles.yaml` / `bora.yaml` / `task.yaml`.

## Bind

```yaml
bindings:
  solver:
    executor: dsh
    model: deepseek-v4-flash
    api_key: deepseek_api_key          # env locator
    options:
      composition: slim               # omit permission → unrestricted local bash/fs
      # permission: read-only         # or workspace-write | danger-full-access
```

`options.permission` is plugin-owned (same pattern as `composition`). Allowed
values: `read-only` | `workspace-write` | `danger-full-access`. Setting it
loads the sandboxed composition (`dsh-fs-sandbox` + `dsh-sandbox-policy` +
`dsh-sandbox-local`) and passes `DSH_PERMISSION_MODE`. Omit it to keep today's
slim / unrestricted local tools. Invalid values fail closed at materialize —
no spawn.

The bundled `dsh-jsonrpc-agent` (`deepseek-harness-sdk==0.1.0rc6`) ships
`dsh-fs-sandbox` but **not** `dsh-bash-sandbox`. The sandboxed tree therefore
keeps `dsh-bash-local`. File-tool writes are fenced; a bash redirect can still
write. Do not claim bash confinement on this runtime.

Batch approval is `never` in the sandboxed tree so an unattended `bora run`
cannot hang on a permission prompt. This is a DSH file-effect policy, not
BORA isolation. L1 Docker + landlock / Seatbelt may fail to start
(`SANDBOX_UNAVAILABLE`); that fails closed. Do not claim `isolated` from this
knob.

Same harness; switch only via profiles or
`--set '/bindings/<role>/options/permission="read-only"'`.

## Journeys smoke (L1, real API)

```bash
uv run bora plugin install plugins/dsh
unset BORA_OFFLINE_AGENT
uv run bora run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.yaml
# file-effect policy (file-tool writes denied; bash can still write):
# uv run bora run examples/journeys --task terminal-jsonl-agg \
#   --profiles examples/journeys/profiles.dsh.read-only.yaml
```

## Recognition ≠ Ready ≠ bind

- **install** → Recognition only (`plugin list` / executor visible)
- **profiles `executor: dsh`** → bind (+ model / api_key locator)
- **L1 Ready** → `image_contribute` bake installs the SDK wheels +
  `bora-executor-dsh`; invoke is **docker exec** with projected `DEEPSEEK_API_KEY`

Host SPI success is not L1 Ready. Offline (`BORA_OFFLINE_AGENT=1`) fail-closes
without spawning the runtime.
