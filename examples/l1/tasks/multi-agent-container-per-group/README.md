# multi-agent-container-per-group

Docker L1 **container-per-group** multi-actor package (Spec 18).

- Two groups (`analysis`, `execution`) → two Agent containers.
- Cross-group text only via Harness memory / prompt (no RW volume).
- SDK `actor_id` is the isolation principal; profile selects executor template.

```bash
uv run ageval run examples/l1 --task multi-agent-container-per-group \
  --task multi-agent-container-per-group
```
