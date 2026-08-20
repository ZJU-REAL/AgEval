# dsh — DeepSeek Harness executor plugin

External `ageval.plugin/1` package. **Not** first-party ageval core.

Drives [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) over
the official Python JSON-RPC SDK (`deepseek-harness-sdk` + bundled
`dsh-jsonrpc-agent`). This is **not** ACP: DSH's shipped ACP wire is too thin
for ageval evidence (no tools / reasoning / usage; model is not on
`config_options`).

The parent does not import the harness. It injects the `environment` service
(`exec`, `upload`), uploads the worker into the box, and runs it with
`host.exec`. Credentials stay locators until invoke, then project into the
exec env as `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`.

Profile `model` is passed on `initialize`. Sessions persist under the Attempt
home (`/attempt/home/dsh-sessions`), not the task workspace.

## Install

```bash
uv sync --extra dsh          # local kind: the box Python is this interpreter
uv run ageval plugin install plugins/dsh
uv run ageval lock examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.yaml --probe
```

Install updates `$AGEVAL_HOME/plugins` (default `~/.ageval/plugins`) only — **never**
edits `profiles.yaml` / `ageval.yaml` / `task.yaml`.

## Bind

```yaml
format: ageval.profiles/1
environment: docker
agent_profiles:
  solver:
    executor: dsh
    extensions:
      - plugin: dsh
        options:
          composition: slim               # omit permission → unrestricted local bash/fs
          # permission: read-only         # or workspace-write | danger-full-access
      - plugin: docker
    model: deepseek-v4-flash
    api_key: ${deepseek_api_key}          # env locator
```

`options.permission` is plugin-owned (same pattern as `composition`). Allowed
values: `read-only` | `workspace-write` | `danger-full-access`. Setting it
loads the sandboxed composition (`dsh-fs-sandbox` + `dsh-sandbox-policy` +
`dsh-sandbox-local`) and passes `DSH_PERMISSION_MODE`. Omit it to keep today's
slim / unrestricted local tools. Invalid values fail closed at materialize —
no spawn.

`options.max_tokens` is also plugin-owned. Omit / blank / `null` → do **not**
pass `max_tokens` into DeepSeek Harness (adapter default). A positive integer
is forwarded on the worker request. Anything else (≤0, bool, string, float)
fails closed at materialize. GLM Coding Plan’s completion window is 131072;
the adapter default 256000 is rejected there — set `max_tokens: 8192` (or
another value in range) on that profile.

```yaml
        options:
          composition: slim
          max_tokens: 8192    # omit this key to keep the adapter default
```

The bundled `dsh-jsonrpc-agent` (`deepseek-harness-sdk==0.1.0rc6`) ships
`dsh-fs-sandbox` but **not** `dsh-bash-sandbox`. The sandboxed tree therefore
keeps `dsh-bash-local`. File-tool writes are fenced; a bash redirect can still
write. Do not claim bash confinement on this runtime.

Batch approval is `never` in the sandboxed tree so an unattended `ageval run`
cannot hang on a permission prompt. This is a DSH file-effect policy, not
ageval isolation. Docker + landlock / Seatbelt may fail to start
(`SANDBOX_UNAVAILABLE`); that fails closed. Do not claim `isolated` from this
knob.

Same `run.py`; switch only via profiles or
`--set '/bindings/<role>/options/permission="read-only"'`.

## Journeys smoke (real API)

```bash
uv run ageval plugin install plugins/dsh
unset AGEVAL_OFFLINE_AGENT
uv run ageval run examples/journeys --task terminal-jsonl-agg \
  --profiles examples/journeys/profiles.dsh.yaml
# file-effect policy (file-tool writes denied; bash can still write):
# uv run ageval run examples/journeys --task terminal-jsonl-agg \
#   --profiles examples/journeys/profiles.dsh.read-only.yaml
```

Evidence for a successful invoke includes worker metadata
`execution_location: attempt-container`. A kind that cannot `exec` fails at
`ageval lock`, not mid-invoke.

## Recognition ≠ this host can run ≠ image baked

- **install** → Recognition only (`plugin list` / executor visible)
- **`host_requires`** → local kind needs `deepseek_harness` on this interpreter (`uv sync --extra dsh`); docker bake installs the wheels in-image
- **profiles `executor: dsh`** → exclusive slot winner (+ model / api_key locator)
- **`extensions: [{plugin: dsh}]`** → opt-in bake / trajectory collect
- **`--probe`** → binding-aware feasibility; no Agent, no bake
- **image baked** → `Dockerfile.bake` installs `deepseek-harness-sdk` into the box Python. The worker script is uploaded at invoke and run with `host.exec` + projected `DEEPSEEK_API_KEY`

Offline (`AGEVAL_OFFLINE_AGENT=1`) fail-closes without calling the provider.
