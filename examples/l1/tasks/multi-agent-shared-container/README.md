# multi-agent-shared-container

Docker L1 **shared-container** multi-actor package (Spec 18).

- Two actors (`planner`, `reviewer`) share one Agent container with distinct UIDs.
- Harness schedules via SDK `Agent.session(..., actor_id=...)` → ParentAgentService → `docker exec`.
- Mid-loop context is **Harness memory** (Scheme A), not Runtime handoff.
- Optional `shared_write: [workspace/team]` for same-container file collaboration.

```bash
uv run ageval run examples/l1 --task multi-agent-shared-container
```

Requires Docker, L1 base image, and real Codex credentials. Offline:

```bash
AGEVAL_OFFLINE_AGENT=1 uv run ageval run examples/l1 --task multi-agent-shared-container \
  --task multi-agent-shared-container
# expected non-zero (fail closed, no host fallback)
```
