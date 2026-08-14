"""Stdlib HTTP Database Registry + results service.

Endpoints:
  GET  /health
  POST /v1/auth/github/device/code
  POST /v1/auth/github/device/poll
  POST /v1/auth/github/web/start
  POST /v1/auth/github/web/callback
  POST /v1/orgs | GET /v1/orgs | GET /v1/orgs/{id} | DELETE /v1/orgs/{id}
  POST /v1/orgs/join | POST /v1/orgs/{id}/leave
  POST /v1/orgs/{id}/claim | GET|POST /v1/orgs/{id}/members | DELETE .../members/{user}
  GET|POST /v1/orgs/{id}/invite-keys | DELETE /v1/orgs/{id}/invite-keys/{key_id}
  POST /v1/packages
  GET  /v1/packages
  GET  /v1/packages/{id}
  GET  /v1/packages/{id}/versions/{ver}
  GET  /v1/packages/{id}/by-digest/{dig}
  GET  /v1/packages/{id}/by-digest/{dig}/content
  GET  /v1/packages/{id}/by-digest/{dig}/files
  GET  /v1/packages/{id}/by-digest/{dig}/files/{path}
  DELETE /v1/packages/{id}/versions/{ver}
  PATCH /v1/packages/{id}/versions/{ver}   (visibility)
  POST /v1/results/attempts
  GET  /v1/results/attempts
  GET  /v1/results/attempts/{run_id}
  DELETE /v1/results/attempts/{run_id}
  PATCH /v1/results/attempts/{run_id}     (visibility)
  GET  /v1/results/attempts/{run_id}/content
  GET  /v1/results/attempts/{run_id}/files
  GET  /v1/results/attempts/{run_id}/files/{path}
  GET|POST|DELETE /v1/results/attempts/{run_id}/shares
  POST /v1/results/suites
  GET  /v1/results/suites
  GET  /v1/results/suites/{suite_run_id}
  DELETE /v1/results/suites/{suite_run_id}[?with_attempts=1]
  PATCH /v1/results/suites/{suite_run_id}  (visibility)
  GET  /v1/results/suites/{suite_run_id}/content
  GET|POST|DELETE /v1/results/suites/{suite_run_id}/shares

Scopes: registry:publish | results:upload | admin (read-private legacy ignored for ACL)
Visibility: public | private. Package private → org member; result private → owner/share.
Owner ops: results → uploaded_by (or admin); packages → org owner (or admin).
Unauthorized private → 404 (not 403). Suite results: no suite-level PASS authority.
Blob GC: delete meta first; drop blob only when digest has zero remaining refs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
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

from services.registry.access import AccessPolicy  # noqa: E402
from services.registry.envload import load_env_file  # noqa: E402
from services.registry.errors import RegistryAppError  # noqa: E402
from services.registry.routes import match_route  # noqa: E402
from services.registry.store import (  # noqa: E402
    ADMIN_SCOPES,
    FilesystemBlobStore,
    MemoryBlobStore,
    MetadataStore,
    PostgresMetadataStore,
    PostgresTokenStore,
    S3BlobStore,
    SqliteTokenStore,
    TokenInfo,
)

from bora.registry.media_types import (  # noqa: E402
    ATTEMPT_RESULT_MEDIA_TYPE as RESULT_MEDIA_TYPE,
)
from bora.registry.media_types import SUITE_RESULT_MEDIA_TYPE  # noqa: E402

MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 64 MiB hard top for v1


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
        self.access = AccessPolicy(meta=meta)
        from services.registry.auth_service import AuthService
        from services.registry.org_service import OrgService
        from services.registry.package_service import PackageService
        from services.registry.result_service import ResultService

        self.auth = AuthService(
            tokens,
            meta=meta,
            github_client_id=github_client_id,
            github_client_secret=github_client_secret,
            github_login_allowlist=github_login_allowlist or frozenset(),
        )
        self.packages = PackageService(meta, blobs, self.access, max_upload=max_upload)
        self.results = ResultService(meta, blobs, self.access, max_upload=max_upload)
        self.orgs = OrgService(meta, self.access)
        self.max_upload = max_upload


def _cors_headers(handler: BaseHTTPRequestHandler) -> None:
    """Optional CORS for Hub SPA (different origin). Env: BORA_REGISTRY_CORS_ORIGIN.

    Default ``*`` for local Hub; set a concrete origin in production. Never
    reflects credentials into logs.
    """
    origin = (os.environ.get("BORA_REGISTRY_CORS_ORIGIN") or "*").strip() or "*"
    handler.send_header("Access-Control-Allow-Origin", origin)
    handler.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
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


def _app_error(handler: BaseHTTPRequestHandler, exc: RegistryAppError) -> None:
    _json_response(handler, exc.http_status, exc.payload())


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

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            qs = parse_qs(parsed.query)
            matched = match_route(method, path)
            if matched is None:
                _json_response(self, 404, {"error": "not_found", "message": "unknown path"})
                return
            route, kwargs = matched
            handler = getattr(self, f"_{route.name}")
            token = _bearer(self)
            auth = state.auth.auth_for(token)
            denied = state.access.enforce_route_access(route.access, auth, kwargs=kwargs)
            if denied is not None:
                status, body = denied
                _json_response(self, status, body)
                return
            if route.access != "none":
                kwargs["auth"] = auth
            if route.pass_qs:
                kwargs["qs"] = qs
            handler(**kwargs)

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def do_DELETE(self) -> None:  # noqa: N802
            self._dispatch("DELETE")

        def do_PATCH(self) -> None:  # noqa: N802
            self._dispatch("PATCH")

        def _health(self) -> None:
            _json_response(self, 200, {"ok": True, "service": "bora-registry"})

        # ---- OAuth -------------------------------------------------------

        def _auth_web_start(self) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.auth.web_start(
                    redirect_uri=str(body.get("redirect_uri") or "").strip()
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _auth_web_callback(self) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.auth.web_callback(
                    code=str(body.get("code") or "").strip(),
                    state=str(body.get("state") or "").strip(),
                    redirect_uri=str(body.get("redirect_uri") or "").strip(),
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _auth_device_code(self) -> None:
            try:
                payload = state.auth.device_code()
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _auth_device_poll(self) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                status, payload = state.auth.device_poll(
                    device_code=str(body.get("device_code") or "")
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, status, payload)

        # ---- packages ----------------------------------------------------

        def _publish_package(self, *, auth: TokenInfo) -> None:
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
            try:
                payload = state.packages.publish(meta=meta, archive=archive, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 201, payload)

        def _release_draft(self, *, database_id: str, auth: TokenInfo) -> None:
            body = self._read_json_body()
            if body is None:
                body = {}
            try:
                payload = state.packages.release_draft(
                    database_id=database_id,
                    auth=auth,
                    visibility=str(body.get("visibility") or "") or None,
                    replace=bool(body.get("replace")),
                    version=str(body.get("version") or "") or None,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 201, payload)

        def _list_packages(self, *, auth: TokenInfo, qs: dict[str, list[str]]) -> None:
            try:
                mine_raw = (qs.get("mine") or [""])[0]
                payload = state.packages.list_packages(
                    auth=auth,
                    prefix=(qs.get("database_id_prefix") or [None])[0],
                    visibility=(qs.get("visibility") or [None])[0],
                    version=(qs.get("version") or [None])[0],
                    package_kind=(qs.get("package_kind") or [None])[0],
                    mine=str(mine_raw).strip().lower() in {"1", "true", "yes"},
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _list_package_versions(self, *, database_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.packages.list_versions(database_id=database_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _serve_meta(
            self,
            *,
            database_id: str,
            version: str | None,
            package_digest: str | None,
            auth: TokenInfo,
        ) -> None:
            try:
                payload = state.packages.serve_meta(
                    database_id=database_id,
                    version=version,
                    package_digest=package_digest,
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _serve_content(
            self,
            *,
            database_id: str,
            package_digest: str,
            auth: TokenInfo,
        ) -> None:
            try:
                data, row = state.packages.serve_content(
                    database_id=database_id,
                    package_digest=package_digest,
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Bora-Blob-Digest", row.blob_digest)
            self.end_headers()
            self.wfile.write(data)

        def _serve_package_files_list(
            self,
            *,
            database_id: str,
            auth: TokenInfo,
            package_digest: str | None = None,
            version: str | None = None,
        ) -> None:
            try:
                payload = state.packages.list_files(
                    database_id=database_id,
                    auth=auth,
                    package_digest=package_digest,
                    version=version,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _serve_package_file(
            self,
            *,
            database_id: str,
            file_path: str,
            auth: TokenInfo,
            package_digest: str | None = None,
            version: str | None = None,
        ) -> None:
            try:
                payload = state.packages.read_file(
                    database_id=database_id,
                    file_path=file_path,
                    auth=auth,
                    package_digest=package_digest,
                    version=version,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _read_multipart_archive(self) -> tuple[dict[str, Any], bytes] | None:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > state.max_upload:
                _json_response(
                    self,
                    413,
                    {"error": "payload_too_large", "message": f"max {state.max_upload} bytes"},
                )
                return None
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
                return None
            return meta, archive

        def _read_json_body(self) -> dict[str, Any] | None:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad JSON"})
                return None
            if not isinstance(body, dict):
                _json_response(self, 400, {"error": "invalid_request", "message": "bad JSON"})
                return None
            return body

        # ---- results -----------------------------------------------------

        def _upload_attempt(self, *, auth: TokenInfo) -> None:
            parsed = self._read_multipart_archive()
            if parsed is None:
                return
            meta, archive = parsed
            try:
                payload = state.results.upload_attempt(meta=meta, archive=archive, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 201, payload)

        def _list_attempts(self, *, auth: TokenInfo, qs: dict[str, list[str]]) -> None:
            try:
                payload = state.results.list_attempts(
                    auth=auth,
                    database_id=(qs.get("database_id") or [None])[0],
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _serve_attempt_meta(self, *, run_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.results.serve_attempt_meta(run_id=run_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _serve_attempt_content(self, *, run_id: str, auth: TokenInfo) -> None:
            try:
                data, row = state.results.serve_attempt_content(run_id=run_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Bora-Blob-Digest", row.blob_digest)
            self.send_header("X-Bora-Media-Type", RESULT_MEDIA_TYPE)
            self.end_headers()
            self.wfile.write(data)

        def _serve_attempt_files_list(self, *, run_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.results.list_attempt_files(run_id=run_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _serve_attempt_file(self, *, run_id: str, file_path: str, auth: TokenInfo) -> None:
            try:
                payload = state.results.read_attempt_file(
                    run_id=run_id, file_path=file_path, auth=auth
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _upload_suite(self, *, auth: TokenInfo) -> None:
            parsed = self._read_multipart_archive()
            if parsed is None:
                return
            meta, archive = parsed
            try:
                payload = state.results.upload_suite(meta=meta, archive=archive, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 201, payload)

        def _list_suites(self, *, auth: TokenInfo, qs: dict[str, list[str]]) -> None:
            try:
                board_raw = (qs.get("board") or [""])[0]
                payload = state.results.list_suites(
                    auth=auth,
                    database_id=(qs.get("database_id") or [None])[0],
                    board=str(board_raw).strip().lower() in {"1", "true", "yes"},
                    uploaded_by=(qs.get("uploaded_by") or [None])[0],
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _serve_suite_meta(self, *, suite_run_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.results.serve_suite_meta(suite_run_id=suite_run_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _serve_suite_content(self, *, suite_run_id: str, auth: TokenInfo) -> None:
            try:
                data, row = state.results.serve_suite_content(suite_run_id=suite_run_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Bora-Blob-Digest", row.blob_digest)
            self.send_header("X-Bora-Media-Type", SUITE_RESULT_MEDIA_TYPE)
            self.end_headers()
            self.wfile.write(data)

        # ---- org ---------------------------------------------------------

        def _create_org(self, *, auth: TokenInfo) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.orgs.create(
                    name=str(body.get("name") or ""),
                    display_name=str(body.get("display_name") or ""),
                    is_claimable=bool(body.get("is_claimable", False)),
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 201, payload)

        def _list_orgs(self, *, auth: TokenInfo) -> None:
            try:
                payload = state.orgs.list_for_user(auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _get_org(self, *, org_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.orgs.get_public(org_id=org_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _patch_org(self, *, org_id: str, auth: TokenInfo) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.orgs.patch(
                    org_id=org_id,
                    display_name=body.get("display_name"),
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _patch_package_display_name(self, *, database_id: str, auth: TokenInfo) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.packages.patch_display_name(
                    database_id=database_id,
                    display_name=body.get("display_name"),
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _claim_org(self, *, org_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.orgs.claim(org_id=org_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _create_invite_key(self, *, org_id: str, auth: TokenInfo) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.orgs.create_invite(
                    org_id=org_id,
                    max_uses=body.get("max_uses"),
                    expires_at=body.get("expires_at"),
                    expires_in_days=body.get("expires_in_days"),
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 201, payload)

        def _list_invite_keys(self, *, org_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.orgs.list_invites(org_id=org_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _revoke_invite_key(self, *, org_id: str, key_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.orgs.revoke_invite(org_id=org_id, key_id=key_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _join_org_with_invite(self, *, auth: TokenInfo) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.orgs.join(
                    invite_key=str(body.get("invite_key") or ""),
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _list_org_members(self, *, org_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.orgs.list_members(org_id=org_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _add_org_member(self, *, org_id: str, auth: TokenInfo) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.orgs.add_member(
                    org_id=org_id,
                    user_id=str(body.get("user_id") or ""),
                    role=str(body.get("role") or "member"),
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 201, payload)

        def _remove_org_member(self, *, org_id: str, user_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.orgs.remove_member(org_id=org_id, user_id=user_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _leave_org(self, *, org_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.orgs.leave(org_id=org_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _delete_org(self, *, org_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.orgs.delete(org_id=org_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        # ---- result shares -----------------------------------------------

        def _list_result_shares(self, *, result_kind: str, result_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.results.list_shares(
                    result_kind=result_kind, result_id=result_id, auth=auth
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _add_result_share(self, *, result_kind: str, result_id: str, auth: TokenInfo) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.results.add_share(
                    result_kind=result_kind,
                    result_id=result_id,
                    target_type=str(body.get("target_type") or ""),
                    target_id=str(body.get("target_id") or ""),
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 201, payload)

        def _remove_result_share(
            self, *, result_kind: str, result_id: str, auth: TokenInfo
        ) -> None:
            body = self._read_json_body()
            if body is None:
                return
            try:
                payload = state.results.remove_share(
                    result_kind=result_kind,
                    result_id=result_id,
                    target_type=str(body.get("target_type") or ""),
                    target_id=str(body.get("target_id") or ""),
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _delete_attempt(self, *, run_id: str, auth: TokenInfo) -> None:
            try:
                payload = state.results.delete_attempt(run_id=run_id, auth=auth)
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _delete_suite(
            self, *, suite_run_id: str, auth: TokenInfo, qs: dict[str, list[str]]
        ) -> None:
            with_attempts = (qs.get("with_attempts") or ["0"])[0] in {
                "1",
                "true",
                "yes",
            }
            try:
                payload = state.results.delete_suite(
                    suite_run_id=suite_run_id,
                    with_attempts=with_attempts,
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _patch_visibility_body(self) -> str | None:
            body = self._read_json_body()
            if body is None:
                return None
            visibility = str(body.get("visibility") or "").strip()
            if visibility not in {"public", "private"}:
                _json_response(
                    self,
                    400,
                    {
                        "error": "invalid_request",
                        "message": "visibility must be public or private",
                    },
                )
                return None
            return visibility

        def _patch_attempt(self, *, run_id: str, auth: TokenInfo) -> None:
            visibility = self._patch_visibility_body()
            if visibility is None:
                return
            try:
                payload = state.results.patch_attempt(
                    run_id=run_id, visibility=visibility, auth=auth
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _patch_suite(self, *, suite_run_id: str, auth: TokenInfo) -> None:
            visibility = self._patch_visibility_body()
            if visibility is None:
                return
            try:
                payload = state.results.patch_suite(
                    suite_run_id=suite_run_id, visibility=visibility, auth=auth
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _delete_package_release(
            self, *, database_id: str, version: str, auth: TokenInfo
        ) -> None:
            try:
                payload = state.packages.delete_release(
                    database_id=database_id, version=version, auth=auth
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

        def _patch_package_release(
            self, *, database_id: str, version: str, auth: TokenInfo
        ) -> None:
            visibility = self._patch_visibility_body()
            if visibility is None:
                return
            try:
                payload = state.packages.patch_visibility(
                    database_id=database_id,
                    version=version,
                    visibility=visibility,
                    auth=auth,
                )
            except RegistryAppError as exc:
                _app_error(self, exc)
                return
            _json_response(self, 200, payload)

    return Handler


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
    tokens.add(token, ADMIN_SCOPES, github_user="bootstrap")
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
    tokens.add(token, ADMIN_SCOPES, github_user="bootstrap")
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
