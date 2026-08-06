"""Stdlib HTTP server for the local Database viewer SPA + JSON API."""

from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from bora.config.errors import ConfigError
from bora.viewer import browse, jobs

# Default bind: loopback only.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def static_dir() -> Path:
    """Locate SPA assets: Vite ``apps/viewer/dist`` or wheel package data.

    Wheel packaging maps ``apps/viewer/dist`` → ``bora/viewer/static`` (see pyproject).
    """
    env = Path(__file__).resolve()
    repo_dist = env.parents[3] / "apps" / "viewer" / "dist"
    pkg_data = env.parent / "static"
    for candidate in (repo_dist, pkg_data):
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    raise FileNotFoundError(
        "viewer SPA not found (from apps/viewer: pnpm build → dist/)"
    )


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _error(handler: BaseHTTPRequestHandler, status: int, code: str, message: str) -> None:
    _json(handler, status, {"error": code, "message": message})


def make_handler(database_root: Path, assets: Path) -> type[BaseHTTPRequestHandler]:
    root = database_root.resolve(strict=False)
    assets = assets.resolve(strict=False)

    class ViewerHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # Quiet by default; still useful on stderr for debugging.
            sys_stderr = __import__("sys").stderr
            sys_stderr.write(f"{self.address_string()} - {format % args}\n")

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            qs = parse_qs(parsed.query)

            if path == "/api/health":
                _json(self, 200, {"ok": True, "service": "bora-viewer"})
                return
            if path == "/api/database":
                self._api_database()
                return
            if path == "/api/commands":
                task_id = (qs.get("task_id") or [None])[0]
                self._api_commands(task_id)
                return
            if path == "/api/jobs":
                self._api_jobs_list()
                return
            if path.startswith("/api/jobs/"):
                self._api_jobs(path)
                return
            if path.startswith("/api/tasks/"):
                self._api_tasks(path, qs)
                return

            # Static SPA (client-side routes fall through to index.html)
            if path in {"/", "/index.html"} or not path.startswith("/api/"):
                # Prefer real assets when present; otherwise SPA shell
                rel = path.lstrip("/")
                if rel and ".." not in Path(rel).parts:
                    candidate = (assets / rel).resolve(strict=False)
                    try:
                        candidate.relative_to(assets)
                        if candidate.is_file():
                            mime, _ = mimetypes.guess_type(str(candidate))
                            self._serve_file(
                                candidate, mime or "application/octet-stream"
                            )
                            return
                    except ValueError:
                        pass
                self._serve_file(assets / "index.html", "text/html; charset=utf-8")
                return

        def _serve_file(self, path: Path, content_type: str) -> None:
            try:
                data = path.read_bytes()
            except OSError:
                _error(self, 404, "not_found", "static asset missing")
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def _api_database(self) -> None:
            try:
                overview = browse.database_overview(root)
                overview["commands"] = browse.commands_for(root)
                _json(self, 200, overview)
            except ConfigError as exc:
                _error(self, 400, exc.error_code, str(exc))

        def _api_commands(self, task_id: str | None) -> None:
            try:
                if task_id:
                    # Validate membership
                    browse.task_detail(root, task_id)
                _json(self, 200, {"commands": browse.commands_for(root, task_id=task_id)})
            except ConfigError as exc:
                _error(self, 400, exc.error_code, str(exc))

        def _api_jobs_list(self) -> None:
            try:
                _json(self, 200, jobs.list_jobs(root))
            except ConfigError as exc:
                _error(self, 400, exc.error_code, str(exc))

        def _api_jobs(self, path: str) -> None:
            # /api/jobs/{job_id}
            # /api/jobs/{job_id}/tasks/{task_id}
            rest = path[len("/api/jobs/") :]
            parts = [p for p in rest.split("/") if p]
            if not parts:
                _error(self, 404, "not_found", "job id required")
                return
            job_id = parts[0]
            try:
                if len(parts) == 1:
                    _json(self, 200, jobs.get_job(root, job_id))
                    return
                if len(parts) == 3 and parts[1] == "tasks":
                    _json(self, 200, jobs.get_job_task(root, job_id, parts[2]))
                    return
            except ConfigError as exc:
                status = 404 if "unknown" in exc.error_code else 400
                _error(self, status, exc.error_code, str(exc))
                return
            _error(self, 404, "not_found", "unknown jobs API path")

        def _api_tasks(self, path: str, qs: dict[str, list[str]]) -> None:
            # /api/tasks/{id}
            # /api/tasks/{id}/tree
            # /api/tasks/{id}/file?path=...
            rest = path[len("/api/tasks/") :]
            parts = [p for p in rest.split("/") if p]
            if not parts:
                _error(self, 404, "not_found", "task id required")
                return
            task_id = parts[0]
            try:
                if len(parts) == 1:
                    _json(self, 200, browse.task_detail(root, task_id))
                    return
                if len(parts) == 2 and parts[1] == "tree":
                    _json(self, 200, browse.file_tree(root, task_id))
                    return
                if len(parts) == 2 and parts[1] == "file":
                    rel = (qs.get("path") or [None])[0]
                    if not rel:
                        _error(self, 400, "invalid_request", "path query required")
                        return
                    _json(self, 200, browse.read_task_file(root, task_id, rel))
                    return
            except ConfigError as exc:
                status = 404 if exc.error_code in {"unknown_task", "invalid_package"} else 400
                if "unknown" in exc.error_code:
                    status = 404
                _error(self, status, exc.error_code, str(exc))
                return
            _error(self, 404, "not_found", "unknown task API path")

    return ViewerHandler


def serve_viewer(
    database_ref: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    block: bool = True,
) -> dict[str, Any]:
    """Start the local viewer. Returns connection info.

    When *block* is True (CLI default), serve forever until KeyboardInterrupt.
    """
    root = browse.open_database(database_ref)
    # Validate package early
    browse.database_overview(root)
    assets = static_dir()
    handler = make_handler(root, assets)
    server = ThreadingHTTPServer((host, port), handler)
    # If port 0, OS assigns.
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    info = {
        "ok": True,
        "url": url,
        "host": actual_host,
        "port": actual_port,
        "database_id": browse.database_overview(root)["database_id"],
        "root": str(root),
    }

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    if block:
        # Operator-facing startup line (stdout so CLI capture is easy).
        print(
            json.dumps(
                {
                    "ok": True,
                    "url": url,
                    "database_id": info["database_id"],
                    "root": info["root"],
                    "message": "viewer listening; Ctrl+C to stop",
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
    else:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        info["server"] = server
        info["thread"] = thread

    return info
