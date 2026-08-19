# executor-image-upstream

L1 package **Dockerfile path B**: `environment/Dockerfile` starts from upstream
`python:3.12-slim-bookworm` and runs `environment/install-executors.sh` to install
the same first-party CLIs.

## Run

```bash
export glm_coding_api_key=...
uv run ageval lock examples/l1 --task executor-image-upstream
uv run ageval run  examples/l1 --task executor-image-upstream
```

First run builds a larger package image (installs Node + CLIs).
