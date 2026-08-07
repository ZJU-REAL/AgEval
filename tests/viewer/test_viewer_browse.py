"""Viewer helpers + HTTP surface (Jobs API + SPA; no package-file browser)."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

import pytest

from bora.viewer import browse
from bora.viewer.server import make_handler, serve_viewer, static_dir

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


def test_static_dir_when_built() -> None:
    """``static_dir()`` requires a local ``pnpm build`` (dist is gitignored)."""
    try:
        d = static_dir()
    except FileNotFoundError:
        pytest.skip("apps/viewer/dist not built (run: cd apps/viewer && pnpm build)")
    assert (d / "index.html").is_file()
    assert (d / "assets").is_dir()


def test_serve_viewer_bind_in_use_includes_host_port(tmp_path: Path) -> None:
    """Port conflict must name the bind address (OS strerror often omits it)."""
    assets = _minimal_spa(tmp_path)
    holder = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(SUITE, assets))
    host, port = holder.server_address[:2]
    thread = threading.Thread(target=holder.serve_forever, daemon=True)
    thread.start()
    try:
        want_url = f"http://{host}:{port}/"
        with (
            patch("bora.viewer.server.static_dir", return_value=assets),
            pytest.raises(OSError, match=r"address already in use: http://") as ei,
        ):
            serve_viewer(
                SUITE,
                host=str(host),
                port=int(port),
                open_browser=False,
                block=False,
            )
        msg = str(ei.value)
        assert want_url in msg
        assert "--port" in msg
    finally:
        holder.shutdown()
        holder.server_close()


def _minimal_spa(tmp_path: Path) -> Path:
    """CI-safe SPA shell (no Vite build required)."""
    root = tmp_path / "spa"
    root.mkdir()
    (root / "index.html").write_text(
        "<!doctype html><html><head><title>BORA Viewer</title></head>"
        '<body><div id="root"></div></body></html>\n',
        encoding="utf-8",
    )
    (root / "assets").mkdir()
    (root / "assets" / "app.js").write_text("// test stub\n", encoding="utf-8")
    return root


@pytest.fixture()
def viewer_server(tmp_path: Path):
    assets = _minimal_spa(tmp_path)
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
