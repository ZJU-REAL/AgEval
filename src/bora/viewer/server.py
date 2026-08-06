"""Stdlib HTTP server for the local Database viewer SPA + Jobs JSON API."""

from __future__ import annotations

import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from bora.config.errors import ConfigError
from bora.viewer import browse, jobs, trials

# Default bind: loopback only.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def static_dir() -> Path:
    """Locate SPA under monorepo ``apps/viewer/dist`` (build artifact, gitignored).

    Optional fallback: package-adjacent ``static/`` if a release process copies the SPA.
    Run ``pnpm build`` in ``apps/viewer`` for local ``bora view``.
    """
    env = Path(__file__).resolve()
    repo_dist = env.parents[3] / "apps" / "viewer" / "dist"
    pkg_data = env.parent / "static"
    for candidate in (repo_dist, pkg_data):
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    raise FileNotFoundError("viewer SPA not found (from apps/viewer: pnpm build → dist/)")


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
            sys.stderr.write(f"{self.address_string()} - {format % args}\n")

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)

            if path == "/api/health":
                _json(self, 200, {"ok": True, "service": "bora-viewer"})
                return
            if path == "/api/jobs":
                self._api_jobs_list()
                return
            if path.startswith("/api/jobs/"):
                self._api_jobs(path)
                return
            if path.startswith("/api/"):
                _error(self, 404, "not_found", "unknown API path")
                return

            # Static SPA (client-side routes fall through to index.html)
            rel = path.lstrip("/")
            if rel and ".." not in Path(rel).parts:
                candidate = (assets / rel).resolve(strict=False)
                try:
                    candidate.relative_to(assets)
                    if candidate.is_file():
                        mime, _ = mimetypes.guess_type(str(candidate))
                        self._serve_file(candidate, mime or "application/octet-stream")
                        return
                except ValueError:
                    pass
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

        def _api_jobs_list(self) -> None:
            try:
                _json(self, 200, jobs.list_jobs(root))
            except ConfigError as exc:
                _error(self, 400, exc.error_code, str(exc))

        def _api_jobs(self, path: str) -> None:
            # /api/jobs/{job_id}
            # /api/jobs/{job_id}/tasks/{task_id}
            # /api/jobs/{job_id}/tasks/{task_id}/trials
            # /api/jobs/{job_id}/tasks/{task_id}/trials/{run_id}
            # /api/jobs/{job_id}/tasks/{task_id}/trials/{run_id}/tree|file|trajectory
            rest = path[len("/api/jobs/") :]
            parts = [p for p in rest.split("/") if p]
            if not parts:
                _error(self, 404, "not_found", "job id required")
                return
            job_id = parts[0]
            query = urlparse(self.path).query
            q = trials.parse_query(query)
            try:
                if len(parts) == 1:
                    _json(self, 200, jobs.get_job(root, job_id))
                    return
                if len(parts) == 3 and parts[1] == "tasks":
                    # Trial-enriched listing (suite summary + local evidence)
                    task_id = parts[2]
                    payload = trials.list_task_trials(root, job_id, task_id)
                    base = jobs.get_job_task(root, job_id, task_id)
                    base["trials"] = payload["trials"]
                    base["note"] = payload.get("note") or base.get("note")
                    _json(self, 200, base)
                    return
                if len(parts) >= 4 and parts[1] == "tasks" and parts[3] == "trials":
                    task_id = parts[2]
                    if len(parts) == 4:
                        _json(self, 200, trials.list_task_trials(root, job_id, task_id))
                        return
                    run_id = parts[4]
                    if len(parts) == 5:
                        _json(self, 200, trials.get_trial(root, job_id, task_id, run_id))
                        return
                    if len(parts) == 6 and parts[5] == "tree":
                        _json(
                            self,
                            200,
                            trials.trial_tree(
                                root,
                                job_id,
                                task_id,
                                run_id,
                                scope=q.get("scope", "root"),
                            ),
                        )
                        return
                    if len(parts) == 6 and parts[5] == "file":
                        rel = q.get("path") or ""
                        if not rel:
                            _error(self, 400, "invalid_package", "path query required")
                            return
                        _json(
                            self,
                            200,
                            trials.trial_file(root, job_id, task_id, run_id, relpath=rel),
                        )
                        return
                    if len(parts) == 6 and parts[5] == "trajectory":
                        _json(
                            self,
                            200,
                            trials.trial_trajectory(root, job_id, task_id, run_id),
                        )
                        return
            except ConfigError as exc:
                status = 404 if "unknown" in exc.error_code else 400
                _error(self, status, exc.error_code, str(exc))
                return
            _error(self, 404, "not_found", "unknown jobs API path")

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
    # Validate package early; reuse for startup metadata.
    overview = browse.database_overview(root)
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
        "database_id": overview["database_id"],
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
