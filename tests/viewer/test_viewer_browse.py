"""Viewer helpers + HTTP surface (Jobs API + SPA; no package-file browser)."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from bora.viewer import browse
from bora.viewer.server import make_handler, static_dir

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


def test_database_overview_suite_min() -> None:
    ov = browse.database_overview(SUITE)
    assert ov["database_id"] == "test/suite-min"
    assert ov["task_count"] >= 3
    assert "alpha" in ov["task_ids"]


def test_commands_include_run_task() -> None:
    cmds = browse.commands_for(SUITE, task_id="alpha")
    assert "bora run" in cmds["run_task"]
    assert "--task alpha" in cmds["run_task"]
    assert "bora lock" in cmds["lock_task"]


def test_static_dir_exists() -> None:
    d = static_dir()
    assert (d / "index.html").is_file()
    # Vite production build: hashed assets under dist/assets/
    assert (d / "assets").is_dir()


@pytest.fixture()
def viewer_server():
    assets = static_dir()
    handler = make_handler(SUITE, assets)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def _get_json(url: str) -> dict:
    with urlopen(url, timeout=5) as resp:  # noqa: S310 — local test server
        return json.loads(resp.read().decode("utf-8"))


def test_http_health_jobs_and_spa(viewer_server: str) -> None:
    base = viewer_server
    health = _get_json(f"{base}/api/health")
    assert health["ok"] is True
    assert health["service"] == "bora-viewer"

    jobs_payload = _get_json(f"{base}/api/jobs")
    assert "items" in jobs_payload
    assert jobs_payload["count"] >= 0
    assert "commands" in jobs_payload

    # SPA shell (React root; Jobs UI mounts client-side)
    with urlopen(f"{base}/", timeout=5) as resp:  # noqa: S310
        html = resp.read().decode("utf-8")
    assert "BORA Viewer" in html
    assert 'id="root"' in html


def test_http_removed_package_browse_404(viewer_server: str) -> None:
    """Old package-file browse endpoints are not part of the product surface."""
    for path in (
        "/api/database",
        "/api/commands",
        "/api/tasks/alpha",
        "/api/tasks/alpha/tree",
        "/api/tasks/alpha/file?path=task.yaml",
    ):
        with pytest.raises(HTTPError) as ei:
            urlopen(f"{viewer_server}{path}", timeout=5)  # noqa: S310
        assert ei.value.code == 404
