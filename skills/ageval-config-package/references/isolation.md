# Isolation notes for package authors

## Gold / evaluation material

- Put hidden labels under `evaluation/` (or package paths never mounted to Agent).
- On Docker L1, package view filters evaluation material from harness/agent.
- Evaluator receives allowlisted staged inputs only after writer barrier.

## Provider

- `provider.kind: local` — L0 path; assurance claims stay l0 unless package is L1.
- `provider.kind: docker` — L1 orchestration. **Package must ship `environment/Dockerfile`**
  (or `provider.dockerfile` relative path). Default official base:
  `FROM ageval-attempt:l1` — build-time bake-in of minimum ACP **entries** (engine + ACP
  inlet for Mode 1): codex / claude-code / pi / opencode / grok-build
  (see docs/design/05-runtime/provider-l1.md).
  Upstream base: `FROM <image>` then install required ACP entries in that Dockerfile.
  Secrets never baked into image layers.
- Coding agents on L1: `executor: acp` + `- plugin: acp` / `options.entry`; parent ACP client +
  `docker exec` placement — no private CLI scrape.

## L1 Dockerfile depth tiers (conversion)

| Tier | When | Pattern |
| --- | --- | --- |
| **Thin** | Official base already has engines + ACP entries; task needs no extra system deps | `FROM ageval-attempt:l1` only (+ optional explicit `COPY` of package paths the container must see) |
| **Heavy** | Upstream image needs apt/pip/lang runtimes not on the official base | Same `FROM ageval-attempt:l1` (or documented upstream base) **+ migrated `RUN`** layers at **build** time |

**Forbid as parity default:** runtime `apt-get` / floating `pip install` / `npm i` / `npx`
inside the Attempt after start. Bake deps in the image; keep invoke path offline-capable
for those tools.

### `FROM ageval-attempt:l1` is not the upstream runtime

The official Attempt image is **CPython 3.12 + baked ACP entries**. It is **not**
the upstream bench’s Python, conda env, or pinned wheels. If the package
Dockerfile `FROM`s this base (instead of the vendor instance image):

1. **Do not** copy upstream `pip install foo` unpinned. Latest wheels on 3.12
   often delete APIs the checkout still imports (e.g. Jinja2 3.1 dropped
   `environmentfilter`; urllib3 2 / astroid 3 break old requests / pylint).
2. **Pin to what the checkout imports**, not “whatever resolves today”. Prefer
   the upstream image’s versions or a range the tree actually supports.
3. **Gate at image build**, not first eval: `python -c "from jinja2 import …"`
   (or the equivalent import) so a bad pin fails `docker build`, not a 20‑min
   agent run.
4. **One extra dump for every repo is wrong.** Astropy headers on a Django /
   Sympy image do not make those suites collectable; use per-repo (or
   per-era) extras.
5. **Collection / conftest ImportError is eval ERROR**, not FAIL. FAIL is
   “tests ran, F2P/P2P missed”. Do not treat a broken env as a model miss.
6. **`host_requires` / `ageval lock --probe` do not catch this.** They are
   host-side. In-image eval deps are the package Dockerfile’s job.

If the checkout cannot run on 3.12 even with pins, say so in `provenance` /
package notes — do not claim official-image parity from a successful build.

### `data/` → `seed_l1_workspace` auto-seed

For **simple file-into-workspace** needs (prompts, starter code, agent-visible fixtures):

1. Put files under `tasks/<id>/data/`.
2. Runtime L1 `seed_l1_workspace` copies those files into the Attempt workspace host path.
3. Prefer this over baking content into image layers.

Use Dockerfile `COPY` only when content must be an **image-layer** artifact (system files,
non-workspace layout, build-time material). Do not invent package “setup hooks” in Core.

### `solution/` (offline fixture)

- Default: **not** seeded to Agent.
- Offline / `AGEVAL_L1_USE_SOLUTION=1` may copy `solution/*` into workspace and set
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
FROM ageval-attempt:l1
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
- Treat `FROM ageval-attempt:l1` + unpinned `pip install` as equivalent to the
  upstream instance image.
