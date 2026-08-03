# BORA Skills (for coding agents)

Short operational paths for agents. **Design authority remains** [`docs/design/`](../docs/design/). Skills only describe **shipped** surfaces.

## Load path

From the repository root, read:

| Skill | Path | Use when |
| --- | --- | --- |
| Platform overview | [`platform/SKILL.md`](platform/SKILL.md) | First entry: authority, red lines, evidence grades |
| CLI | [`cli/SKILL.md`](cli/SKILL.md) | `bora lock` / `run` / `evidence` / exit codes |
| Config / package | [`config-package/SKILL.md`](config-package/SKILL.md) | Writing `bora.yaml` and package layout |
| SDK / harness | [`sdk-harness/SKILL.md`](sdk-harness/SKILL.md) | `AgentSession`, tools, terminals |

Do **not** invent commands or fields not present in production. Prefer linking design sections over restating them.

## Minimal walkthrough

1. `uv sync --frozen --all-packages`
2. `uv run bora lock examples/core/config-minimal --task config-minimal`
3. Open `skills/config-package/SKILL.md` and note how to change `parameters` / profiles without harness executor branches
4. Optional agent path: `uv run bora run examples/core/attempt-trajectory --task attempt-trajectory` then inspect `Result.logs`

## Antipatterns (forbidden)

- Treating trajectory as PASS
- Putting secrets in yaml / lock / evidence
- Naming adapters after Benchmarks or tasks
- Claiming `isolated` / `real-benchmark-verified` from one happy path
