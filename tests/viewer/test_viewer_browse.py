"""Local Database viewer browse + HTTP API tests (#21)."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest

from bora.config.errors import ConfigError
from bora.viewer import browse
from bora.viewer.server import make_handler, static_dir

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"
CORE = REPO / "examples" / "core"


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


def test_task_detail_and_tree() -> None:
    detail = browse.task_detail(SUITE, "alpha")
    assert detail["task_id"] == "alpha"
    assert detail["task_yaml"] is not None
    assert "task_id" in detail["task_yaml"]
    tree = browse.file_tree(SUITE, "alpha")
    assert tree["tree"]["type"] == "dir"
    names = {c["name"] for c in tree["tree"]["children"] if c.get("type") == "file"}
    assert "task.yaml" in names
    assert "harness.py" in names


def test_read_task_file_text() -> None:
    data = browse.read_task_file(SUITE, "alpha", "task.yaml")
    assert data["kind"] == "text"
    assert data["content"] and "task_id" in data["content"]


def test_path_traversal_rejected() -> None:
    with pytest.raises(ConfigError):
        browse.read_task_file(SUITE, "alpha", "../beta/task.yaml")
    with pytest.raises(ConfigError):
        browse.read_task_file(SUITE, "alpha", "../../bora.yaml")


def test_static_dir_exists() -> None:
    d = static_dir()
    assert (d / "index.html").is_file()
    assert (d / "app.js").is_file()


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


def test_http_api_list_detail_file(viewer_server: str) -> None:
    base = viewer_server
    db = _get_json(f"{base}/api/database")
    assert db["database_id"] == "test/suite-min"
    assert db["task_count"] >= 3
    assert "run_suite" in db["commands"]

    detail = _get_json(f"{base}/api/tasks/alpha")
    assert detail["task_id"] == "alpha"
    assert "run_task" in detail["commands"]

    tree = _get_json(f"{base}/api/tasks/alpha/tree")
    assert tree["tree"]["type"] == "dir"

    file_data = _get_json(f"{base}/api/tasks/alpha/file?path=task.yaml")
    assert file_data["kind"] == "text"
    assert "format" in file_data["content"]

    # SPA shell
    with urlopen(f"{base}/", timeout=5) as resp:  # noqa: S310
        html = resp.read().decode("utf-8")
    assert "BORA Viewer" in html
    assert 'id="task-list"' in html


def test_http_unknown_task_404(viewer_server: str) -> None:
    from urllib.error import HTTPError

    with pytest.raises(HTTPError) as ei:
        urlopen(f"{viewer_server}/api/tasks/no-such-task", timeout=5)  # noqa: S310
    assert ei.value.code == 404
