"""Stdlib HTTP Database Registry + results service.

Endpoints:
  GET  /health
  POST /v1/auth/github/device/code
  POST /v1/auth/github/device/poll
  POST /v1/packages
  GET  /v1/packages
  GET  /v1/packages/{id}
  GET  /v1/packages/{id}/versions/{ver}
  GET  /v1/packages/{id}/by-digest/{dig}
  GET  /v1/packages/{id}/by-digest/{dig}/content
  GET  /v1/packages/{id}/by-digest/{dig}/files
  GET  /v1/packages/{id}/by-digest/{dig}/files/{path}
  POST /v1/results/attempts
  GET  /v1/results/attempts
  GET  /v1/results/attempts/{run_id}
  GET  /v1/results/attempts/{run_id}/content
  POST /v1/results/suites
  GET  /v1/results/suites
  GET  /v1/results/suites/{suite_run_id}
  GET  /v1/results/suites/{suite_run_id}/content

Scopes: registry:publish | read-private | results:upload | results:read | admin
Visibility: public | private only. Private unauthorized → 404 (not 403).
Suite results: observational aggregates only — no suite-level PASS authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

# Allow `python -m services.registry.app` from repo root.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from services.registry.envload import load_env_file  # noqa: E402
from services.registry.oauth_github import (  # noqa: E402
    GitHubOAuthError,
    fetch_user,
    poll_access_token,
    request_device_code,
)
from services.registry.store import (  # noqa: E402
    ADMIN_SCOPES,
    DEFAULT_LOGIN_SCOPES,
    AttemptResultRow,
    FilesystemBlobStore,
    MemoryBlobStore,
    MetadataStore,
    PostgresMetadataStore,
    PostgresTokenStore,
    ReleaseRow,
    S3BlobStore,
    SqliteTokenStore,
    SuiteResultRow,
    attempt_to_dict,
    now,
    release_to_dict,
    suite_to_dict,
)

MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 64 MiB hard top for v1
RESULT_MEDIA_TYPE = "application/vnd.bora.attempt-result.v1.tar+gzip"
SUITE_RESULT_MEDIA_TYPE = "application/vnd.bora.suite-result.v1.tar+gzip"


class RegistryState:
    def __init__(
        self,
        *,
        meta: Any,
        blobs: Any,
        tokens: Any,
        max_upload: int = MAX_UPLOAD_BYTES,
        github_client_id: str | None = None,
        github_client_secret: str | None = None,
        github_login_allowlist: frozenset[str] | None = None,
    ) -> None:
        self.meta = meta
        self.blobs = blobs
        self.tokens = tokens
        self.max_upload = max_upload
        self.github_client_id = github_client_id
        self.github_client_secret = github_client_secret
        # Empty allowlist = refuse OAuth token issue (fail closed). Bootstrap token still works.
        self.github_login_allowlist = github_login_allowlist or frozenset()


def _cors_headers(handler: BaseHTTPRequestHandler) -> None:
    """Optional CORS for Hub SPA (different origin). Env: BORA_REGISTRY_CORS_ORIGIN.

    Default ``*`` for local Hub; set a concrete origin in production. Never
    reflects credentials into logs.
    """
    origin = (os.environ.get("BORA_REGISTRY_CORS_ORIGIN") or "*").strip() or "*"
    handler.send_header("Access-Control-Allow-Origin", origin)
    handler.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    if origin != "*":
        handler.send_header("Vary", "Origin")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    _cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(body)


def _bearer(handler: BaseHTTPRequestHandler) -> str | None:
    auth = handler.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _parse_multipart(body: bytes, content_type: str) -> dict[str, bytes]:
    """Parse multipart/form-data without corrupting binary parts.

    Only strip framing CRLF at the part boundary — never rstrip the payload
    (gzip archives may legitimately end in 0x0d / 0x0a).
    """
    m = re.search(r"boundary=([^;]+)", content_type)
    if not m:
        raise ValueError("missing multipart boundary")
    boundary = m.group(1).strip().encode()
    parts = body.split(b"--" + boundary)
    out: dict[str, bytes] = {}
    for part in parts:
        if part in (b"", b"--\r\n", b"--", b"\r\n", b"--\r\n", b""):
            continue
        if part.startswith(b"--"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        # Final boundary part may end with "--" after optional CRLF.
        if part.endswith(b"--"):
            part = part[:-2]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        header_blob, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = header_blob.decode("utf-8", errors="replace")
        name_m = re.search(r'name="([^"]+)"', headers)
        if not name_m:
            continue
        # Framing already removed above; keep payload bytes intact.
        out[name_m.group(1)] = data
    return out


def _can_list_private_packages(scopes: frozenset[str]) -> bool:
    # publish may verify private releases they just wrote; not a results scope.
    return "read-private" in scopes or "admin" in scopes or "registry:publish" in scopes


def _can_list_private_results(scopes: frozenset[str]) -> bool:
    # results:upload does NOT imply private read (independent scope model).
    return "results:read" in scopes or "admin" in scopes


def make_handler(state: RegistryState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            # Path-only; never log Authorization or tokens.
            sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

        def do_OPTIONS(self) -> None:  # noqa: N802
            # CORS preflight for Hub SPA (browser Authorization header).
            self.send_response(204)
            _cors_headers(self)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            qs = parse_qs(parsed.query)

            if path == "/health":
                _json_response(self, 200, {"ok": True, "service": "bora-registry"})
                return

            token = _bearer(self)
            scopes = state.tokens.scopes_for(token)

            if path == "/v1/packages":
                self._list_packages(scopes=scopes, qs=qs)
                return

            m = re.fullmatch(r"/v1/packages/([^/]+(?:/[^/]+)*)", path)
            # Exact package id list — but not versions/by-digest paths.
            if m and "/versions/" not in path and "/by-digest/" not in path:
                # path is /v1/packages/{id} possibly with slashes in id
                # Prefer more specific routes first below; this branch only if no subpath.
                rest = path[len("/v1/packages/") :]
                if "/versions/" not in rest and "/by-digest/" not in rest and rest:
                    self._list_package_versions(database_id=rest, scopes=scopes)
                    return

            m = re.fullmatch(r"/v1/packages/(.+)/versions/([^/]+)", path)
            if m:
                self._serve_meta(
                    database_id=m.group(1),
                    version=m.group(2),
                    package_digest=None,
                    scopes=scopes,
                )
                return
            m = re.fullmatch(
                r"/v1/packages/(.+)/by-digest/(sha256:[0-9a-f]{64})/content",
                path,
            )
            if m:
                self._serve_content(
                    database_id=m.group(1),
                    package_digest=m.group(2),
                    scopes=scopes,
                )
                return
            # Package files list (#38) — more specific than bare by-digest meta.
            m = re.fullmatch(
                r"/v1/packages/(.+)/by-digest/(sha256:[0-9a-f]{64})/files",
                path,
            )
            if m:
                self._serve_package_files_list(
                    database_id=m.group(1),
                    package_digest=m.group(2),
                    scopes=scopes,
                )
                return
            m = re.fullmatch(
                r"/v1/packages/(.+)/by-digest/(sha256:[0-9a-f]{64})/files/(.+)",
                path,
            )
            if m:
                self._serve_package_file(
                    database_id=m.group(1),
                    package_digest=m.group(2),
                    file_path=m.group(3),
                    scopes=scopes,
                )
                return
            # Version-aliased files (resolve → digest internally).
            m = re.fullmatch(
                r"/v1/packages/(.+)/versions/([^/]+)/files",
                path,
            )
            if m:
                self._serve_package_files_list(
                    database_id=m.group(1),
                    version=m.group(2),
                    scopes=scopes,
                )
                return
            m = re.fullmatch(
                r"/v1/packages/(.+)/versions/([^/]+)/files/(.+)",
                path,
            )
            if m:
                self._serve_package_file(
                    database_id=m.group(1),
                    version=m.group(2),
                    file_path=m.group(3),
                    scopes=scopes,
                )
                return
            m = re.fullmatch(
                r"/v1/packages/(.+)/by-digest/(sha256:[0-9a-f]{64})",
                path,
            )
            if m:
                self._serve_meta(
                    database_id=m.group(1),
                    version=None,
                    package_digest=m.group(2),
                    scopes=scopes,
                )
                return

            if path == "/v1/results/attempts":
                self._list_attempts(scopes=scopes, qs=qs)
                return
            m = re.fullmatch(r"/v1/results/attempts/([^/]+)/content", path)
            if m:
                self._serve_attempt_content(run_id=m.group(1), scopes=scopes)
                return
            m = re.fullmatch(r"/v1/results/attempts/([^/]+)", path)
            if m:
                self._serve_attempt_meta(run_id=m.group(1), scopes=scopes)
                return

            if path == "/v1/results/suites":
                self._list_suites(scopes=scopes, qs=qs)
                return
            m = re.fullmatch(r"/v1/results/suites/([^/]+)/content", path)
            if m:
                self._serve_suite_content(suite_run_id=m.group(1), scopes=scopes)
                return
            m = re.fullmatch(r"/v1/results/suites/([^/]+)", path)
            if m:
                self._serve_suite_meta(suite_run_id=m.group(1), scopes=scopes)
                return

            _json_response(self, 404, {"error": "not_found", "message": "unknown path"})

        def do_POST(self) -> None:  # noqa: N802
            path = unquote(self.path.split("?", 1)[0])

            if path == "/v1/auth/github/device/code":
                self._auth_device_code()
                return
            if path == "/v1/auth/github/device/poll":
                self._auth_device_poll()
                return
            if path == "/v1/packages":
                self._publish_package()
                return
            if path == "/v1/results/attempts":
                self._upload_attempt()
                return
            if path == "/v1/results/suites":
                self._upload_suite()
                return
            _json_response(self, 404, {"error": "not_found", "message": "unknown path"})

        # ---- OAuth -------------------------------------------------------

        def _auth_device_code(self) -> None:
            if not state.github_client_id:
                _json_response(
                    self,
                    503,
                    {
                        "error": "oauth_not_configured",
                        "message": "BORA_GITHUB_CLIENT_ID not set",
                    },
                )
                return
            try:
                dc = request_device_code(client_id=state.github_client_id)
            except GitHubOAuthError as exc:
                _json_response(self, 502, {"error": exc.code, "message": exc.message})
                return
            payload = {
                "device_code": dc.device_code,
                "user_code": dc.user_code,
                "verification_uri": dc.verification_uri,
                "expires_in": dc.expires_in,
                "interval": dc.interval,
            }
            if dc.verification_uri_complete:
                payload["verification_uri_complete"] = dc.verification_uri_complete
            _json_response(self, 200, payload)

        def _auth_device_poll(self) -> None:
            if not state.github_client_id or not state.github_client_secret:
                _json_response(
                    self,
                    503,
                    {
                        "error": "oauth_not_configured",
                        "message": "GitHub OAuth client not configured",
                    },
                )
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad JSON"})
                return
            device_code = str(body.get("device_code") or "")
            if not device_code:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": "device_code required"},
                )
                return
            try:
                gh_token = poll_access_token(
                    client_id=state.github_client_id,
                    client_secret=state.github_client_secret,
                    device_code=device_code,
                )
            except GitHubOAuthError as exc:
                _json_response(self, 400, {"error": exc.code, "message": exc.message})
                return
            if gh_token is None:
                _json_response(
                    self,
                    202,
                    {"status": "authorization_pending", "message": "waiting for user"},
                )
                return
            try:
                identity = fetch_user(gh_token)
            except GitHubOAuthError as exc:
                _json_response(self, 502, {"error": exc.code, "message": exc.message})
                return
            allow = state.github_login_allowlist
            if not allow:
                _json_response(
                    self,
                    403,
                    {
                        "error": "login_not_allowed",
                        "message": (
                            "BORA_GITHUB_LOGIN_ALLOWLIST is empty; "
                            "set comma-separated GitHub logins before bora login"
                        ),
                    },
                )
                return
            if identity.login.casefold() not in {u.casefold() for u in allow}:
                _json_response(
                    self,
                    403,
                    {
                        "error": "login_not_allowed",
                        "message": f"GitHub user {identity.login!r} is not on the allowlist",
                    },
                )
                return
            # Issue Registry API token; do not store GitHub access token.
            api_token = secrets.token_urlsafe(32)
            state.tokens.add(
                api_token,
                DEFAULT_LOGIN_SCOPES,
                github_user=identity.login,
            )
            _json_response(
                self,
                200,
                {
                    "token": api_token,
                    "token_type": "bearer",
                    "scopes": sorted(DEFAULT_LOGIN_SCOPES),
                    "github_user": identity.login,
                },
            )

        # ---- packages ----------------------------------------------------

        def _publish_package(self) -> None:
            token = _bearer(self)
            scopes = state.tokens.scopes_for(token)
            if "registry:publish" not in scopes and "admin" not in scopes:
                _json_response(
                    self,
                    401,
                    {"error": "unauthorized", "message": "publish scope required"},
                )
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > state.max_upload:
                _json_response(
                    self,
                    413,
                    {"error": "payload_too_large", "message": f"max {state.max_upload} bytes"},
                )
                return
            body = self.rfile.read(length)
            ctype = self.headers.get("Content-Type") or ""
            try:
                parts = _parse_multipart(body, ctype)
                meta = json.loads(parts["metadata"].decode("utf-8"))
                archive = parts["archive"]
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": f"bad multipart: {exc}"},
                )
                return

            database_id = str(meta.get("database_id") or "")
            version = str(meta.get("version") or "")
            package_digest = str(meta.get("package_digest") or "")
            blob_digest = str(meta.get("blob_digest") or "")
            media_type = str(meta.get("media_type") or "")
            visibility = str(meta.get("visibility") or "private")
            size = int(meta.get("size") or len(archive))
            if visibility not in {"private", "public"}:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad visibility"})
                return
            actual_blob = f"sha256:{hashlib.sha256(archive).hexdigest()}"
            if actual_blob != blob_digest or size != len(archive):
                _json_response(
                    self,
                    400,
                    {"error": "digest_mismatch", "message": "blob digest or size mismatch"},
                )
                return
            try:
                from bora.registry.archive import extract_archive
                from bora.registry.digest import compute_package_digest

                with tempfile.TemporaryDirectory(prefix="bora-reg-") as tmp:
                    extract_archive(archive, Path(tmp))
                    got = compute_package_digest(Path(tmp))
                    if got != package_digest:
                        _json_response(
                            self,
                            400,
                            {
                                "error": "digest_mismatch",
                                "message": "package digest mismatch after extract",
                            },
                        )
                        return
            except Exception as exc:  # noqa: BLE001
                _json_response(
                    self,
                    400,
                    {"error": "invalid_archive", "message": str(exc)},
                )
                return

            row = ReleaseRow(
                database_id=database_id,
                version=version,
                visibility=visibility,
                package_digest=package_digest,
                blob_digest=blob_digest,
                size=size,
                media_type=media_type,
                created_at=now(),
            )
            try:
                state.blobs.put_if_absent(blob_digest, archive, prefix="packages")
                state.meta.insert(row)
            except ValueError:
                _json_response(
                    self,
                    409,
                    {"error": "conflict", "message": "release already exists"},
                )
                return
            _json_response(self, 201, release_to_dict(row))

        def _list_packages(self, *, scopes: frozenset[str], qs: dict[str, list[str]]) -> None:
            include_private = _can_list_private_packages(scopes)
            prefix = (qs.get("database_id_prefix") or [None])[0]
            visibility = (qs.get("visibility") or [None])[0]
            version = (qs.get("version") or [None])[0]
            if visibility is not None and visibility not in {"public", "private"}:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad visibility"})
                return
            rows = state.meta.list_releases(
                database_id_prefix=prefix or None,
                visibility=visibility,
                version=version or None,
                include_private=include_private,
            )
            _json_response(
                self,
                200,
                {"items": [release_to_dict(r) for r in rows]},
            )

        def _list_package_versions(self, *, database_id: str, scopes: frozenset[str]) -> None:
            include_private = _can_list_private_packages(scopes)
            rows = state.meta.list_versions(database_id, include_private=include_private)
            _json_response(
                self,
                200,
                {
                    "database_id": database_id,
                    "items": [release_to_dict(r) for r in rows],
                },
            )

        def _visible_package(self, row: ReleaseRow, scopes: frozenset[str]) -> bool:
            if row.visibility == "public":
                return True
            return _can_list_private_packages(scopes)

        def _serve_meta(
            self,
            *,
            database_id: str,
            version: str | None,
            package_digest: str | None,
            scopes: frozenset[str],
        ) -> None:
            if package_digest:
                row = state.meta.get_by_digest(database_id, package_digest)
            else:
                assert version is not None
                row = state.meta.get_by_version(database_id, version)
            if row is None or not self._visible_package(row, scopes):
                _json_response(self, 404, {"error": "not_found", "message": "release not found"})
                return
            _json_response(self, 200, release_to_dict(row))

        def _serve_content(
            self,
            *,
            database_id: str,
            package_digest: str,
            scopes: frozenset[str],
        ) -> None:
            row = state.meta.get_by_digest(database_id, package_digest)
            if row is None or not self._visible_package(row, scopes):
                _json_response(self, 404, {"error": "not_found", "message": "release not found"})
                return
            data = state.blobs.get(row.blob_digest, prefix="packages")
            if data is None:
                _json_response(self, 404, {"error": "not_found", "message": "blob missing"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Bora-Blob-Digest", row.blob_digest)
            self.end_headers()
            self.wfile.write(data)

        def _resolve_visible_release(
            self,
            *,
            database_id: str,
            scopes: frozenset[str],
            package_digest: str | None = None,
            version: str | None = None,
        ) -> ReleaseRow | None:
            if package_digest:
                row = state.meta.get_by_digest(database_id, package_digest)
            elif version:
                row = state.meta.get_by_version(database_id, version)
            else:
                return None
            if row is None or not self._visible_package(row, scopes):
                return None
            return row

        def _serve_package_files_list(
            self,
            *,
            database_id: str,
            scopes: frozenset[str],
            package_digest: str | None = None,
            version: str | None = None,
        ) -> None:
            from services.registry.package_files import get_or_build_index

            row = self._resolve_visible_release(
                database_id=database_id,
                scopes=scopes,
                package_digest=package_digest,
                version=version,
            )
            if row is None:
                _json_response(self, 404, {"error": "not_found", "message": "release not found"})
                return
            archive = state.blobs.get(row.blob_digest, prefix="packages")
            if archive is None:
                _json_response(self, 404, {"error": "not_found", "message": "blob missing"})
                return
            try:
                index = get_or_build_index(archive, package_digest=row.package_digest)
            except Exception as exc:  # noqa: BLE001
                _json_response(
                    self,
                    500,
                    {"error": "archive_error", "message": f"cannot index package: {exc}"},
                )
                return
            _json_response(
                self,
                200,
                {
                    "database_id": row.database_id,
                    "digest": row.package_digest,
                    "version": row.version,
                    "items": index.list_items(),
                },
            )

        def _serve_package_file(
            self,
            *,
            database_id: str,
            file_path: str,
            scopes: frozenset[str],
            package_digest: str | None = None,
            version: str | None = None,
        ) -> None:
            from services.registry.package_files import (
                MAX_FILE_BYTES,
                PackageFileNotFound,
                PackageFileTooLarge,
                PackagePathError,
                file_payload,
                normalize_package_path,
                read_member,
            )

            row = self._resolve_visible_release(
                database_id=database_id,
                scopes=scopes,
                package_digest=package_digest,
                version=version,
            )
            if row is None:
                _json_response(self, 404, {"error": "not_found", "message": "release not found"})
                return
            try:
                safe_path = normalize_package_path(file_path)
            except PackagePathError as exc:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_path", "message": str(exc)},
                )
                return
            archive = state.blobs.get(row.blob_digest, prefix="packages")
            if archive is None:
                _json_response(self, 404, {"error": "not_found", "message": "blob missing"})
                return
            try:
                data, size = read_member(archive, safe_path, max_bytes=MAX_FILE_BYTES)
            except PackagePathError as exc:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_path", "message": str(exc)},
                )
                return
            except PackageFileNotFound:
                _json_response(
                    self,
                    404,
                    {"error": "not_found", "message": f"file not found: {safe_path}"},
                )
                return
            except PackageFileTooLarge as exc:
                _json_response(
                    self,
                    413,
                    {
                        "error": "payload_too_large",
                        "message": (
                            f"file exceeds {MAX_FILE_BYTES} bytes "
                            f"(path={exc.path}, size={exc.size})"
                        ),
                        "max_bytes": MAX_FILE_BYTES,
                        "path": exc.path,
                        "size": exc.size,
                    },
                )
                return
            payload = file_payload(safe_path, data, size=size, truncated=False)
            _json_response(self, 200, payload)

        # ---- results -----------------------------------------------------

        def _upload_attempt(self) -> None:
            token = _bearer(self)
            scopes = state.tokens.scopes_for(token)
            if "results:upload" not in scopes and "admin" not in scopes:
                _json_response(
                    self,
                    401,
                    {"error": "unauthorized", "message": "results:upload scope required"},
                )
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > state.max_upload:
                _json_response(
                    self,
                    413,
                    {"error": "payload_too_large", "message": f"max {state.max_upload} bytes"},
                )
                return
            body = self.rfile.read(length)
            ctype = self.headers.get("Content-Type") or ""
            try:
                parts = _parse_multipart(body, ctype)
                meta = json.loads(parts["metadata"].decode("utf-8"))
                archive = parts["archive"]
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": f"bad multipart: {exc}"},
                )
                return

            run_id = str(meta.get("run_id") or "")
            database_id = str(meta.get("database_id") or "")
            task_id = str(meta.get("task_id") or "")
            lock_digest = str(meta.get("lock_digest") or "")
            status = str(meta.get("status") or "")
            visibility = str(meta.get("visibility") or "private")
            blob_digest = str(meta.get("blob_digest") or "")
            size = int(meta.get("size") or len(archive))
            if not run_id or not database_id:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": "run_id and database_id required"},
                )
                return
            if visibility not in {"private", "public"}:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad visibility"})
                return
            actual_blob = f"sha256:{hashlib.sha256(archive).hexdigest()}"
            if actual_blob != blob_digest or size != len(archive):
                _json_response(
                    self,
                    400,
                    {"error": "digest_mismatch", "message": "blob digest or size mismatch"},
                )
                return
            # Lightweight secret scan on archive bytes (patterns only; no extraction log).
            if _archive_looks_like_secret_leak(archive):
                _json_response(
                    self,
                    400,
                    {
                        "error": "secret_scan_failed",
                        "message": "archive rejected: possible credential material",
                    },
                )
                return

            row = AttemptResultRow(
                run_id=run_id,
                database_id=database_id,
                task_id=task_id,
                lock_digest=lock_digest,
                status=status,
                visibility=visibility,
                blob_digest=blob_digest,
                size=size,
                created_at=now(),
            )
            try:
                state.blobs.put_if_absent(blob_digest, archive, prefix="results")
                state.meta.insert_attempt(row)
            except ValueError:
                _json_response(
                    self,
                    409,
                    {"error": "conflict", "message": "attempt result already exists"},
                )
                return
            _json_response(self, 201, attempt_to_dict(row))

        def _visible_result(self, row: AttemptResultRow, scopes: frozenset[str]) -> bool:
            if row.visibility == "public":
                return True
            return _can_list_private_results(scopes)

        def _list_attempts(self, *, scopes: frozenset[str], qs: dict[str, list[str]]) -> None:
            include_private = _can_list_private_results(scopes)
            database_id = (qs.get("database_id") or [None])[0]
            rows = state.meta.list_attempts(
                database_id=database_id or None,
                include_private=include_private,
            )
            _json_response(
                self,
                200,
                {"items": [attempt_to_dict(r) for r in rows]},
            )

        def _serve_attempt_meta(self, *, run_id: str, scopes: frozenset[str]) -> None:
            row = state.meta.get_attempt(run_id)
            if row is None or not self._visible_result(row, scopes):
                _json_response(self, 404, {"error": "not_found", "message": "attempt not found"})
                return
            _json_response(self, 200, attempt_to_dict(row))

        def _serve_attempt_content(self, *, run_id: str, scopes: frozenset[str]) -> None:
            row = state.meta.get_attempt(run_id)
            if row is None or not self._visible_result(row, scopes):
                _json_response(self, 404, {"error": "not_found", "message": "attempt not found"})
                return
            data = state.blobs.get(row.blob_digest, prefix="results")
            if data is None:
                _json_response(self, 404, {"error": "not_found", "message": "blob missing"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Bora-Blob-Digest", row.blob_digest)
            self.send_header("X-Bora-Media-Type", RESULT_MEDIA_TYPE)
            self.end_headers()
            self.wfile.write(data)

        # ---- suite results -----------------------------------------------

        def _visible_suite(self, row: SuiteResultRow, scopes: frozenset[str]) -> bool:
            if row.visibility == "public":
                return True
            return _can_list_private_results(scopes)

        def _upload_suite(self) -> None:
            token = _bearer(self)
            scopes = state.tokens.scopes_for(token)
            if "results:upload" not in scopes and "admin" not in scopes:
                _json_response(
                    self,
                    401,
                    {"error": "unauthorized", "message": "results:upload scope required"},
                )
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > state.max_upload:
                _json_response(
                    self,
                    413,
                    {"error": "payload_too_large", "message": f"max {state.max_upload} bytes"},
                )
                return
            body = self.rfile.read(length)
            ctype = self.headers.get("Content-Type") or ""
            try:
                parts = _parse_multipart(body, ctype)
                meta = json.loads(parts["metadata"].decode("utf-8"))
                archive = parts["archive"]
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": f"bad multipart: {exc}"},
                )
                return

            suite_run_id = str(meta.get("suite_run_id") or "")
            database_id = str(meta.get("database_id") or "")
            database_version = str(meta.get("database_version") or "")
            visibility = str(meta.get("visibility") or "private")
            blob_digest = str(meta.get("blob_digest") or "")
            size = int(meta.get("size") or len(archive))
            if not suite_run_id or not database_id:
                _json_response(
                    self,
                    400,
                    {
                        "error": "invalid_request",
                        "message": "suite_run_id and database_id required",
                    },
                )
                return
            if visibility not in {"private", "public"}:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad visibility"})
                return
            # Reject any client-supplied suite PASS authority field.
            if "pass" in meta or "verdict" in meta or meta.get("suite_pass") is not None:
                _json_response(
                    self,
                    400,
                    {
                        "error": "invalid_request",
                        "message": "suite-level PASS/verdict fields are not accepted",
                    },
                )
                return
            actual_blob = f"sha256:{hashlib.sha256(archive).hexdigest()}"
            if actual_blob != blob_digest or size != len(archive):
                _json_response(
                    self,
                    400,
                    {"error": "digest_mismatch", "message": "blob digest or size mismatch"},
                )
                return
            if _archive_looks_like_secret_leak(archive):
                _json_response(
                    self,
                    400,
                    {
                        "error": "secret_scan_failed",
                        "message": "archive rejected: possible credential material",
                    },
                )
                return

            metrics = meta.get("metrics") if isinstance(meta.get("metrics"), dict) else {}
            task_refs = meta.get("task_refs") if isinstance(meta.get("task_refs"), list) else []
            try:
                pass_rate = float(meta.get("pass_rate", metrics.get("pass_rate", 0.0)))
                mean_score = float(meta.get("mean_score", metrics.get("mean_score", 0.0)))
            except (TypeError, ValueError):
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": "pass_rate/mean_score must be numeric"},
                )
                return
            try:
                exit_code = int(meta.get("exit_code", 0))
            except (TypeError, ValueError):
                exit_code = 0

            # #42 config fingerprint projection from suite summary (optional).
            config_payload: dict[str, Any] = {}
            if meta.get("config_fingerprint"):
                config_payload["config_fingerprint"] = str(meta["config_fingerprint"])
            if "config_homogeneous" in meta:
                config_payload["config_homogeneous"] = bool(meta.get("config_homogeneous"))
            actors_raw = meta.get("actors_summary")
            if isinstance(actors_raw, list):
                config_payload["actors_summary"] = [
                    a for a in actors_raw if isinstance(a, dict)
                ]

            row = SuiteResultRow(
                suite_run_id=suite_run_id,
                database_id=database_id,
                database_version=database_version,
                visibility=visibility,
                pass_rate=pass_rate,
                mean_score=mean_score,
                metrics_json=json.dumps(metrics, sort_keys=True),
                tasks_json=json.dumps(task_refs, sort_keys=True),
                agent_label=str(meta.get("agent_label") or ""),
                model_label=str(meta.get("model_label") or ""),
                blob_digest=blob_digest,
                size=size,
                exit_code=exit_code,
                created_at=now(),
                config_json=json.dumps(config_payload, sort_keys=True),
            )
            try:
                state.blobs.put_if_absent(blob_digest, archive, prefix="suite-results")
                state.meta.insert_suite(row)
            except ValueError:
                _json_response(
                    self,
                    409,
                    {"error": "conflict", "message": "suite result already exists"},
                )
                return
            _json_response(self, 201, suite_to_dict(row))

        def _list_suites(self, *, scopes: frozenset[str], qs: dict[str, list[str]]) -> None:
            include_private = _can_list_private_results(scopes)
            database_id = (qs.get("database_id") or [None])[0]
            rows = state.meta.list_suites(
                database_id=database_id or None,
                include_private=include_private,
            )
            _json_response(
                self,
                200,
                {"items": [suite_to_dict(r) for r in rows]},
            )

        def _serve_suite_meta(self, *, suite_run_id: str, scopes: frozenset[str]) -> None:
            row = state.meta.get_suite(suite_run_id)
            if row is None or not self._visible_suite(row, scopes):
                _json_response(self, 404, {"error": "not_found", "message": "suite not found"})
                return
            _json_response(self, 200, suite_to_dict(row))

        def _serve_suite_content(self, *, suite_run_id: str, scopes: frozenset[str]) -> None:
            row = state.meta.get_suite(suite_run_id)
            if row is None or not self._visible_suite(row, scopes):
                _json_response(self, 404, {"error": "not_found", "message": "suite not found"})
                return
            data = state.blobs.get(row.blob_digest, prefix="suite-results")
            if data is None:
                _json_response(self, 404, {"error": "not_found", "message": "blob missing"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Bora-Blob-Digest", row.blob_digest)
            self.send_header("X-Bora-Media-Type", SUITE_RESULT_MEDIA_TYPE)
            self.end_headers()
            self.wfile.write(data)

    return Handler


_SECRET_PATTERNS = (
    re.compile(rb"(?i)-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(rb"(?i)BORA_REGISTRY_TOKEN\s*="),
    re.compile(rb"(?i)github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"(?i)ghp_[A-Za-z0-9]{20,}"),
)


def _archive_looks_like_secret_leak(archive: bytes) -> bool:
    # Scan raw gzip/tar bytes for high-signal credential markers only.
    sample = archive if len(archive) < 4_000_000 else archive[:4_000_000]
    return any(p.search(sample) for p in _SECRET_PATTERNS)


def build_default_state(
    data_dir: Path,
    *,
    bootstrap_token: str | None = None,
    memory_blob: bool = False,
) -> tuple[RegistryState, str]:
    """Zero-dep path: SQLite meta + filesystem (or memory) blob + SQLite tokens."""
    db_path = data_dir / "meta.sqlite3"
    meta = MetadataStore(db_path)
    tokens: Any = SqliteTokenStore(db_path)
    blobs: Any = MemoryBlobStore() if memory_blob else FilesystemBlobStore(data_dir / "blobs")
    token = bootstrap_token or secrets.token_urlsafe(24)
    tokens.add(token, ADMIN_SCOPES)
    return (
        RegistryState(
            meta=meta,
            blobs=blobs,
            tokens=tokens,
            github_client_id=os.environ.get("BORA_GITHUB_CLIENT_ID"),
            github_client_secret=os.environ.get("BORA_GITHUB_CLIENT_SECRET"),
            github_login_allowlist=_parse_login_allowlist(),
        ),
        token,
    )


def _parse_login_allowlist() -> frozenset[str]:
    raw = os.environ.get("BORA_GITHUB_LOGIN_ALLOWLIST") or ""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def build_state_from_env(
    *,
    bootstrap_token: str | None = None,
    force_local: bool = False,
) -> tuple[RegistryState, str]:
    """Prefer Postgres + S3 when env is set; else SQLite/fs under data dir."""
    load_env_file()
    database_url = os.environ.get("BORA_REGISTRY_DATABASE_URL")
    s3_endpoint = os.environ.get("BORA_REGISTRY_S3_ENDPOINT")
    if force_local or not database_url or not s3_endpoint:
        data_dir = (
            Path(os.environ.get("BORA_REGISTRY_DATA_DIR") or ".bora/registry-data")
            .expanduser()
            .resolve()
        )
        data_dir.mkdir(parents=True, exist_ok=True)
        return build_default_state(data_dir, bootstrap_token=bootstrap_token)

    meta = PostgresMetadataStore(database_url)
    tokens = PostgresTokenStore(database_url)
    blobs = S3BlobStore(
        endpoint=s3_endpoint,
        access_key=os.environ.get("BORA_REGISTRY_S3_ACCESS_KEY") or "bora",
        secret_key=os.environ.get("BORA_REGISTRY_S3_SECRET_KEY") or "boraborabora",
        bucket=os.environ.get("BORA_REGISTRY_S3_BUCKET") or "bora",
        region=os.environ.get("BORA_REGISTRY_S3_REGION") or "us-east-1",
    )
    token = bootstrap_token or secrets.token_urlsafe(24)
    tokens.add(token, ADMIN_SCOPES)
    return (
        RegistryState(
            meta=meta,
            blobs=blobs,
            tokens=tokens,
            github_client_id=os.environ.get("BORA_GITHUB_CLIENT_ID"),
            github_client_secret=os.environ.get("BORA_GITHUB_CLIENT_SECRET"),
            github_login_allowlist=_parse_login_allowlist(),
        ),
        token,
    )


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    parser = argparse.ArgumentParser(description="BORA Database Registry service")
    parser.add_argument(
        "--host",
        default=os.environ.get("BORA_REGISTRY_HOST") or "127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BORA_REGISTRY_PORT") or "8700"),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("BORA_REGISTRY_DATA_DIR") or ".bora/registry-data"),
        help="SQLite + filesystem blob root when not using Postgres/S3",
    )
    parser.add_argument(
        "--bootstrap-token",
        default=os.environ.get("BORA_REGISTRY_BOOTSTRAP_TOKEN"),
        help="API token (default: random, printed once to stderr)",
    )
    parser.add_argument(
        "--memory-blob",
        action="store_true",
        help="Use in-memory blob store (tests only)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Force SQLite+filesystem even if Postgres/S3 env is set",
    )
    args = parser.parse_args(argv)

    if args.local or args.memory_blob:
        data_dir = args.data_dir.expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        state, token = build_default_state(
            data_dir,
            bootstrap_token=args.bootstrap_token,
            memory_blob=args.memory_blob,
        )
        backend = "sqlite+memory" if args.memory_blob else "sqlite+filesystem"
    else:
        try:
            state, token = build_state_from_env(
                bootstrap_token=args.bootstrap_token,
                force_local=False,
            )
            database_url = os.environ.get("BORA_REGISTRY_DATABASE_URL")
            s3_endpoint = os.environ.get("BORA_REGISTRY_S3_ENDPOINT")
            backend = "postgres+s3" if database_url and s3_endpoint else "sqlite+filesystem"
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"registry backend init failed: {exc}\n")
            return 1

    handler = make_handler(state)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    sys.stderr.write(
        f"bora-registry listening on http://{args.host}:{args.port} backend={backend}\n"
        f"bootstrap token (store in ~/.bora/credentials; not logged elsewhere): {token}\n"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
