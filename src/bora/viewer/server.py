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
from bora.viewer import browse

# Default bind: loopback only.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def static_dir() -> Path:
    """Locate SPA static assets (monorepo apps/viewer/static or package data)."""
    env = Path(__file__).resolve()
    # src/bora/viewer/server.py → repo root apps/viewer/static
    repo_static = env.parents[3] / "apps" / "viewer" / "static"
    if repo_static.is_dir():
        return repo_static
    # Installed package data: bora/viewer/static next to this module
    pkg_static = env.parent / "static"
    if pkg_static.is_dir():
        return pkg_static
    raise FileNotFoundError(
        "viewer static assets not found (expected apps/viewer/static or package data)"
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

        def log_message(self, fmt: str, *args: object) -> None:
            # Quiet by default; still useful on stderr for debugging.
            sys_stderr = __import__("sys").stderr
            sys_stderr.write(f"{self.address_string()} - {fmt % args}\n")

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
            if path.startswith("/api/tasks/"):
                self._api_tasks(path, qs)
                return

            # Static SPA
            if path in {"/", "/index.html"}:
                self._serve_file(assets / "index.html", "text/html; charset=utf-8")
                return
            # Strip leading slash; never allow escape from assets
            rel = path.lstrip("/")
            if ".." in Path(rel).parts:
                _error(self, 404, "not_found", "unknown path")
                return
            candidate = (assets / rel).resolve(strict=False)
            try:
                candidate.relative_to(assets)
            except ValueError:
                _error(self, 404, "not_found", "unknown path")
                return
            if candidate.is_file():
                mime, _ = mimetypes.guess_type(str(candidate))
                self._serve_file(candidate, mime or "application/octet-stream")
                return
            # SPA fallback
            self._serve_file(assets / "index.html", "text/html; charset=utf-8")

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
