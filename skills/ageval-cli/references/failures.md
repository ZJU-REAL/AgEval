# CLI failure diagnosis

| Symptom | Check |
| --- | --- |
| exit 2, empty stdout on lock | Config error on stderr (`unknown_profile`, schema, `invalid_format` at `/format`) |
| lock `unsupported_capability` / `unsupported executor` | Kind not in `ageval executors` `.supported` — coding agents need `executor: acp` |
| lock `options.entry required` | ACP profile missing `- plugin: acp` / `options.entry` |
| Agent ERROR offline | Expected under `AGEVAL_OFFLINE_AGENT=1` |
| executor unbound on docker | Plugin did not bind to the box (`attach_stdio` / in-box worker). Do not silent host-fallback |
| `image_contribute_unsatisfied` / missing bake | Bound external executor but `config.image_layers` / `Dockerfile.bake` empty — `$ageval-plugin` |
| `nooa_package_missing` / `No module named 'nooa'` | Host needs `uv sync --extra nooa`; docker image bake installs it in-image |
| ACP entry not ready | `ageval executors -v` → that `entry_id` `host_ready` / install pin; no invoke-time `npm i` |
| `credential_missing` | Declared credential env names unset and no `api_key` locator. Required entries fail at `--probe` / session-open; keyless (OAuth) entries warn only |
| e2b / ssh probe not ready | Missing `E2B_API_KEY` or SSH locator — fail-closed, `started: false`. Skip ≠ pass |
| PASS without real model | Forbidden — do not use fixtures as public proof |
| Trajectory empty | Non-empty `agent_profiles` + `run.py` `Agent.session`/`invoke` |
| Resume skipped an ERROR | Default `--resume-suite` skips finished PASS / FAIL / ERROR. Use `--replace-slot --task T` |
| Export fails `unsealed_invocation` | Attempt still running or metadata not terminal |
| Export fails `secret_residual` | Fix source evidence; do not strip secrets by hand in export dir |
| Docker ERROR | Docker daemon, image build, network/creds projection; read result / agent meta under `.ageval/runs/` |

Design: `docs/design/05-runtime/evidence.md`, `docs/design/07-budget-evaluation-failure.md`.
