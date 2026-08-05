# executor-image-official

L1 package **Dockerfile path A**: `environment/Dockerfile` is `FROM bora-attempt:l1`
(official base with codex / pi / opencode / claude-code preinstalled).

## Run

```bash
# ensure base image exists once
uv run python docker/attempt/build.py --platform linux/arm64

export glm_coding_api_key=...   # or repo .env
uv run bora lock examples/l1/executor-image-official --task executor-image-official
uv run bora run  examples/l1/executor-image-official --task executor-image-official
```

Expect PASS with `executor_containment: container` (not parent residual).
