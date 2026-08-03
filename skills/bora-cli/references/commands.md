# CLI command notes

## `bora lock`

- Deterministic JSON on stdout (digest, task_id, resolution, resolved_references).
- No secret values.
- Does not create Run/Attempt or start Agent.

## `bora run`

- One foreground Attempt via production composition root.
- Creates evidence under package `.bora/runs/...` unless overridden internally.
- `logs` is absolute path to Attempt evidence root when available.
- Docker packages use L1 path when `provider.kind: docker`.

## `bora evidence`

- Read-only export of **sealed** invocations.
- Refuses unsealed (running) metadata.
- Writes `manifest.json` with `schema: bora.trajectory.export/1` and `source_digests`.
- Does not change evaluation score.

## `bora campaign`

- Foreground serial matrix; allowlisted `/parameters/*` axes.
- Not full campaign admission/retry policy.

## Control surface

- `submit` / `status` / `cancel` operate on ControlStore records (sketch maturity).
