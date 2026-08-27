"""egress: llm in a real docker agent box: allow bound host, refuse the rest."""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from ageval.environments.protocol import BoxSpec
from ageval.plugins.contrib.docker.host import DockerHost
from ageval.plugins.contrib.docker.images import daemon_available


def _skip_without_docker() -> None:
    if os.environ.get("AGEVAL_SKIP_DOCKER") == "1":
        pytest.skip("AGEVAL_SKIP_DOCKER=1")
    if not daemon_available():
        pytest.skip("docker daemon is not reachable")


def _serve() -> tuple[ThreadingHTTPServer, int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = b"bound-ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            del format, args

    server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, int(server.server_address[1])


@pytest.mark.asyncio
async def test_agent_box_cannot_fetch_arbitrary_url(tmp_path: Path) -> None:
    _skip_without_docker()
    origin, port = _serve()
    spec = BoxSpec(attempt_root=tmp_path / "box", task_root=tmp_path, repo_root=tmp_path)
    host = DockerHost(
        spec=spec,
        options={
            "image": "python:3.12-slim",
            "egress": "llm",
            "egress_allowlist": ["127.0.0.1"],
        },
    )
    script = (
        "import urllib.request, urllib.error\n"
        f"url='http://127.0.0.1:{port}/'\n"
        "print('bound', urllib.request.urlopen(url, timeout=8).read().decode())\n"
        "try:\n"
        "    urllib.request.urlopen('http://example.com/', timeout=8)\n"
        "    print('arbitrary-open')\n"
        "except urllib.error.HTTPError as exc:\n"
        "    print('arbitrary', exc.code)\n"
        "except Exception as exc:\n"
        "    print('arbitrary', type(exc).__name__)\n"
    )
    try:
        await host.preflight()
        await host.start()
        result = await host.exec(["python3", "-c", script], timeout_sec=30)
        assert result.ok, result.stderr or result.stdout
        out = result.stdout
        assert "bound-ok" in out
        assert "arbitrary-open" not in out
        assert "arbitrary 403" in out or "arbitrary" in out
    finally:
        await host.stop(delete=True)
        origin.shutdown()
