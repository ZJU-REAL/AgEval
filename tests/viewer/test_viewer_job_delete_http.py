"""HTTP surface for local Job delete (preview + confirm)."""

from __future__ import annotations

import json
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ageval.viewer.server import make_handler

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "fixtures" / "databases" / "suite-min"


def _minimal_spa(tmp_path: Path) -> Path:
    root = tmp_path / "spa"
    root.mkdir()
    (root / "index.html").write_text(
        "<!doctype html><html><head><title>ageval Viewer</title></head>"
        '<body><div id="root"></div></body></html>\n',
        encoding="utf-8",
    )
    return root


def _clean_db(tmp_path: Path) -> Path:
    db = tmp_path / "db"
    shutil.copytree(SUITE, db, ignore=shutil.ignore_patterns(".ageval"))
    return db


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _seed_attempt(db: Path, run_id: str) -> None:
    _write_json(
        db / ".ageval" / "runs" / run_id / "result.json",
        {"task_id": "alpha", "status": "PASS", "score": 1.0},
    )


def _seed_suite(db: Path, job_id: str, run_ids: list[str]) -> None:
    _write_json(
        db / ".ageval" / "suite-runs" / job_id / "summary.json",
        {
            "schema": "ageval.suite.summary/1",
            "suite_run_id": job_id,
            "tasks": [{"task_id": "alpha", "status": "PASS", "score": 1.0, "run_id": run_ids[0]}],
            "task_refs": [
                {
                    "task_id": "alpha",
                    "status": "PASS",
                    "score": 1.0,
                    "run_id": run_ids[0],
                    "attempt_run_ids": run_ids,
                }
            ],
            "attempts": [{"task_id": "alpha", "run_id": rid} for rid in run_ids],
        },
    )


@pytest.fixture()
def viewer_db(tmp_path: Path):
    db = _clean_db(tmp_path)
    assets = _minimal_spa(tmp_path)
    handler = make_handler(db, assets, cors_origin="http://127.0.0.1:5173")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield db, base
    finally:
        server.shutdown()
        server.server_close()


def _json(url: str, *, method: str = "GET") -> dict:
    req = Request(url, method=method, headers={"Accept": "application/json"})
    with urlopen(req, timeout=5) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def test_http_delete_single(viewer_db: tuple[Path, str]) -> None:
    db, base = viewer_db
    _seed_attempt(db, "run_http_single")
    preview = _json(f"{base}/api/jobs/run_http_single/delete-preview")
    assert preview["kind"] == "single"
    assert preview["can_delete"] is True
    assert preview["confirm_token"]
    with pytest.raises(HTTPError) as missing:
        _json(f"{base}/api/jobs/run_http_single", method="DELETE")
    assert missing.value.code == 400
    deleted = _json(
        f"{base}/api/jobs/run_http_single?confirm={preview['confirm_token']}",
        method="DELETE",
    )
    assert deleted["ok"] is True
    listed = _json(f"{base}/api/jobs")
    assert all(item["job_id"] != "run_http_single" for item in listed["items"])
    assert not (db / ".ageval" / "runs" / "run_http_single").exists()


def test_http_delete_suite_cascade(viewer_db: tuple[Path, str]) -> None:
    db, base = viewer_db
    _seed_suite(db, "suite_http", ["run_http_a", "run_http_b"])
    _seed_attempt(db, "run_http_a")
    _seed_attempt(db, "run_http_b")
    preview = _json(f"{base}/api/jobs/suite_http/delete-preview")
    assert preview["kind"] == "suite"
    assert set(preview["cascade_run_ids"]) >= {"run_http_a", "run_http_b"}
    _json(
        f"{base}/api/jobs/suite_http?confirm={preview['confirm_token']}",
        method="DELETE",
    )
    listed = _json(f"{base}/api/jobs")
    ids = {item["job_id"] for item in listed["items"]}
    assert "suite_http" not in ids
    assert "run_http_a" not in ids
    assert "run_http_b" not in ids


def test_http_refuse_inner_attempt(viewer_db: tuple[Path, str]) -> None:
    db, base = viewer_db
    _seed_suite(db, "suite_http", ["run_inner"])
    _seed_attempt(db, "run_inner")
    preview = _json(f"{base}/api/jobs/run_inner/delete-preview")
    assert preview["can_delete"] is False
    assert preview["error"]["code"] == "job_inner_attempt"
    with pytest.raises(HTTPError) as ei:
        _json(
            f"{base}/api/jobs/run_inner?confirm={preview['confirm_token']}",
            method="DELETE",
        )
    assert ei.value.code == 409


def test_http_refuse_escape(viewer_db: tuple[Path, str]) -> None:
    _db, base = viewer_db
    with pytest.raises(HTTPError) as ei:
        _json(f"{base}/api/jobs/%2e%2e/delete-preview")
    assert ei.value.code == 400


def test_http_cors_allows_delete(viewer_db: tuple[Path, str]) -> None:
    _db, base = viewer_db
    req = Request(
        f"{base}/api/jobs/x",
        method="OPTIONS",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    with urlopen(req, timeout=5) as resp:  # noqa: S310
        allow = resp.headers.get("Access-Control-Allow-Methods") or ""
        assert "DELETE" in allow
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:5173"
