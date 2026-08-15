"""Starlette/uvicorn HTTP pipe for the Registry.

ACL and routing stay in ``Route.access`` + ``RegistryHttpApi``. This module
only terminates HTTP and fans out workers. FastAPI / OpenAPI are out of scope.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Any

from services.registry.http_api import RegistryHttpApi


def build_asgi_app(state: Any) -> Any:
    """Return a Starlette app bound to an already-built ``RegistryState``."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response, StreamingResponse
    from starlette.routing import Route

    api = RegistryHttpApi(state)

    async def endpoint(request: Request) -> Response:
        body = await request.body()
        header_map = {k.decode("latin1"): v.decode("latin1") for k, v in request.scope["headers"]}
        target = request.url.path
        if request.url.query:
            target = f"{target}?{request.url.query}"
        result = api.dispatch(
            method=request.method,
            path=target,
            headers=header_map,
            body=io.BytesIO(body),
            content_length=len(body),
        )
        headers = dict(result.headers)
        if result.stream is not None:

            def _iter() -> Any:
                try:
                    while True:
                        chunk = result.stream.read(64 * 1024)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    result.stream.close()

            return StreamingResponse(
                _iter(),
                status_code=result.status,
                headers=headers,
                media_type=headers.pop("Content-Type", "application/octet-stream"),
            )
        media = headers.pop("Content-Type", "application/json")
        return Response(
            content=result.body,
            status_code=result.status,
            headers=headers,
            media_type=media,
        )

    async def endpoint_any(request: Request) -> Response:
        return await endpoint(request)

    return Starlette(
        routes=[
            Route(
                "/{path:path}",
                endpoint=endpoint_any,
                methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            ),
            Route(
                "/", endpoint=endpoint_any, methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
            ),
        ]
    )


def app_factory() -> Any:
    """Uvicorn ``--factory`` entry: rebuild state per worker from env."""
    from services.registry.app import build_state_from_env
    from services.registry.envload import load_env_file

    load_env_file()
    force_local = (os.environ.get("BORA_REGISTRY_FORCE_LOCAL") or "").strip() in {
        "1",
        "true",
        "yes",
    }
    memory_blob = (os.environ.get("BORA_REGISTRY_MEMORY_BLOB") or "").strip() in {
        "1",
        "true",
        "yes",
    }
    state, token = build_state_from_env(
        bootstrap_token=os.environ.get("BORA_REGISTRY_BOOTSTRAP_TOKEN"),
        force_local=force_local or memory_blob,
        memory_blob=memory_blob,
    )
    # One line per worker so operators can see the token without stdout dumps.
    if token and not os.environ.get("BORA_REGISTRY_BOOTSTRAP_TOKEN"):
        sys.stderr.write(f"worker bootstrap token: {token}\n")
    return build_asgi_app(state)


def serve_uvicorn(
    state: Any,
    *,
    host: str,
    port: int,
    workers: int,
    token: str,
    local: bool,
    memory_blob: bool,
    data_dir: str,
    bootstrap_token: str | None,
) -> int:
    """Run uvicorn. Workers > 1 rebuild state via ``app_factory``."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "uvicorn required for --workers; install with: uv sync --extra registry"
        ) from exc

    if bootstrap_token:
        os.environ["BORA_REGISTRY_BOOTSTRAP_TOKEN"] = bootstrap_token
    elif token:
        os.environ.setdefault("BORA_REGISTRY_BOOTSTRAP_TOKEN", token)
    os.environ["BORA_REGISTRY_DATA_DIR"] = data_dir
    if local:
        os.environ["BORA_REGISTRY_FORCE_LOCAL"] = "1"
    if memory_blob:
        os.environ["BORA_REGISTRY_MEMORY_BLOB"] = "1"

    config_kw: dict[str, Any] = {
        "host": host,
        "port": port,
        "log_level": "warning",
    }
    if workers <= 1:
        app = build_asgi_app(state)
        uvicorn.run(app, **config_kw)
        return 0
    uvicorn.run(
        "services.registry.asgi:app_factory",
        factory=True,
        workers=workers,
        **config_kw,
    )
    return 0
