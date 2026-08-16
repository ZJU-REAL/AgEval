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
- Coding agents on L1: `executor: acp` + `- plugin: acp` / `options.entry`; parent ACP client +
  `docker exec` placement — no private CLI scrape.

## L1 Dockerfile depth tiers (conversion)

| Tier | When | Pattern |
| --- | --- | --- |
| **Thin** | Official base already has engines + ACP entries; task needs no extra system deps | `FROM bora-attempt:l1` only (+ optional explicit `COPY` of package paths the container must see) |
| **Heavy** | Upstream image needs apt/pip/lang runtimes not on the official base | Same `FROM bora-attempt:l1` (or documented upstream base) **+ migrated `RUN`** layers at **build** time |

**Forbid as parity default:** runtime `apt-get` / floating `pip install` / `npm i` / `npx`
inside the Attempt after start. Bake deps in the image; keep invoke path offline-capable
for those tools.

### `data/` → `seed_l1_workspace` auto-seed

For **simple file-into-workspace** needs (prompts, starter code, agent-visible fixtures):

1. Put files under `tasks/<id>/data/`.
2. Runtime L1 `seed_l1_workspace` copies those files into the Attempt workspace host path.
3. Prefer this over baking content into image layers.

Use Dockerfile `COPY` only when content must be an **image-layer** artifact (system files,
non-workspace layout, build-time material). Do not invent package “setup hooks” in Core.

### `solution/` (offline fixture)

- Default: **not** seeded to Agent.
- Offline / `BORA_L1_USE_SOLUTION=1` may copy `solution/*` into workspace and set
  `solution_seed` in L1 meta — author-level offline path only, not production default.

## Dataset `shared/`

- Import contract: Runtime injects **`[task_dir, database_root]`** — **not** the
  `shared/lib` leaf. Authors write `from shared.lib…` / `from lib…`.
- `shared/lib` is for Harness/Evaluator import only — **not** default Agent mount.
- Gold stays under `tasks/*/evaluation/` only; **forbid** gold / `.env` under `shared/`.
- Task members must **not** own top-level name `shared` (`shared/` dir or `shared.py`).
  Same basename under `shared/lib` and `tasks/*/lib` is **allowed**.
- Check with: `uv run python scripts/check_shared_lib_collisions.py <database-root>`.
- L1: **no** Core implicit COPY of `shared/`. L0 path inject **≠** L1 automatic
  availability for the clean evaluator container.

### L0 vs L1 evaluator asymmetry (B1)

| Surface | `shared.lib.*` available? |
| --- | --- |
| L0 harness worker / L0 evaluator subprocess | Yes — Runtime injects Database root |
| L1 Attempt / clean-evaluator container | **Only if** task Dockerfile explicitly `COPY shared/` and sets `PYTHONPATH` so **Database root** (or layout that still exposes package `shared`) is on path |

Same `evaluator.py` with `from shared.lib…` can **pass on L0** and **ImportError on L1**
unless the image recipe includes `shared/`. Do not expect Core to fix that.

### L1 Dockerfile snippet (B3) — matches host inject

When Harness or Evaluator inside the container must import Dataset glue, **declare** it
in the task Dockerfile (Core will not inject):

```dockerfile
FROM bora-attempt:l1
# Build context is typically the Database root (or documented equivalent).
COPY shared/ /attempt/shared/
# Put Database-layout root on path so `import shared` / `shared.lib.*` resolve.
# Do NOT set PYTHONPATH to only /attempt/shared/lib (leaf inject is retired).
ENV PYTHONPATH=/attempt:/attempt/task:${PYTHONPATH}
# Optional: also COPY task sources the container needs under /attempt/task
```

If your layout mounts the whole Database at `/attempt/db`:

```dockerfile
COPY shared/ /attempt/db/shared/
ENV PYTHONPATH=/attempt/db:/attempt/task:${PYTHONPATH}
```

Notes:

- Build context and `COPY` sources are package-owned; paths above are illustrative.
- Do **not** `COPY` `tasks/*/evaluation/` gold into Agent-visible layers.
- Prefer thin image + host-seeded `data/` when files only need to land in workspace.

## Do not

- Rely on “delete field from yaml” as isolation.
- Mount gold into harness “for convenience”.
- Put credentials in package tree.
- Put evaluation gold or host secrets under Database-root `shared/`.
- Own top-level `shared` under a task member (dir or `.py`).
- Depend on bare leaf imports (`from bridge import …`) — use `shared.lib.*`.
- Expect Core to auto-COPY `shared/` into L1 images.
- Use runtime package installs as the default parity path for converted suites.
