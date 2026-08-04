# L1 ACP agent placement (Spec 19 Phase 4)

Parent typed ACP client + `docker exec -u/-w` into image-baked `opencode acp`.

```bash
uv run python docker/attempt/build.py --platform linux/arm64
uv run bora run examples/l1/acp-agent-placement --task acp-agent-placement
```

Expect `assurance:l1`, `execution_location=attempt-container`, `host_fallback_count=0`.
