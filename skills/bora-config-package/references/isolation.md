# Isolation notes for package authors

## Gold / evaluation material

- Put hidden labels under `evaluation/` (or package paths never mounted to Agent).
- On Docker L1, package view filters evaluation material from harness/agent.
- Evaluator receives allowlisted staged inputs only after writer barrier.

## Provider

- `provider.kind: local` — L0 path; assurance claims stay l0 unless package is L1.
- `provider.kind: docker` — L1 orchestration. **Package must ship `environment/Dockerfile`**
  (or `provider.dockerfile` relative path). Default official base:
  `FROM bora-attempt:l1` — build-time bake-in of minimum ACP **entries** (engine + ACP
  inlet for Mode 1): codex / claude-code / pi / opencode / grok-build
  (see docs/design/05-runtime/provider-l1.md).
  Upstream base: `FROM <image>` then install required ACP entries in that Dockerfile.
  Secrets never baked into image layers.
- Coding agents on L1: `executor: acp` + `options.entry`; parent ACP client +
  `docker exec` placement — no private CLI scrape.

## Dataset `shared/` (#65)

- `shared/lib` is for Harness/Evaluator import only — **not** default Agent mount.
- Gold stays under `tasks/*/evaluation/` only; **forbid** gold / `.env` under `shared/`.
- L1: no Core implicit COPY of `shared/`; task `environment/Dockerfile` owns any `COPY`.
- Collision: `shared/lib` vs `tasks/*/lib` top-level names → lock fail. Check with
  `uv run python scripts/check_shared_lib_collisions.py <database-root>`.

## Do not

- Rely on “delete field from yaml” as isolation.
- Mount gold into harness “for convenience”.
- Put credentials in package tree.
- Put evaluation gold or host secrets under Database-root `shared/`.
- Reuse the same top-level module name in `shared/lib` and a task `lib/`.
