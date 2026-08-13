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
import hashlib
import json
import os
import re
import secrets
import sys
import time
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
from services.registry.oauth_github import (  # noqa: E402
    GitHubOAuthError,
    build_web_authorize_url,
    exchange_web_code,
    fetch_user,
    poll_access_token,
    request_device_code,
)
from services.registry.routes import match_route  # noqa: E402
from services.registry.store import (  # noqa: E402
    ADMIN_SCOPES,
    DEFAULT_LOGIN_SCOPES,
    FilesystemBlobStore,
    MemoryBlobStore,
    MetadataStore,
    PostgresMetadataStore,
    PostgresTokenStore,
    S3BlobStore,
    SqliteTokenStore,
    TokenInfo,
    _normalize_user_id,
    invite_key_to_dict,
    membership_to_dict,
    now,
    org_to_dict,
)

from bora.registry.media_types import (  # noqa: E402
    ATTEMPT_RESULT_MEDIA_TYPE as RESULT_MEDIA_TYPE,
)
from bora.registry.media_types import SUITE_RESULT_MEDIA_TYPE  # noqa: E402

_ORG_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?$")

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

        self.auth = AuthService(tokens)
        self.packages = PackageService(meta, blobs, self.access, max_upload=max_upload)
        self.results = ResultService(meta, blobs, self.access, max_upload=max_upload)
        self.orgs = OrgService(meta, self.access)
        self.max_upload = max_upload
        self.github_client_id = github_client_id
        self.github_client_secret = github_client_secret
        # Empty allowlist = refuse OAuth token issue (fail closed). Bootstrap token still works.
        self.github_login_allowlist = github_login_allowlist or frozenset()
        # Web OAuth (Hub): state -> {redirect_uri, created_at}
        self.oauth_web_states: dict[str, dict[str, Any]] = {}


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


def _is_admin(scopes: frozenset[str]) -> bool:
    return AccessPolicy.is_admin(scopes)


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
            auth = state.tokens.auth_for(token)
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

        def _allowed_web_redirect(self, redirect_uri: str) -> bool:
            """Local Hub defaults + optional BORA_GITHUB_WEB_REDIRECT_URIS allowlist."""
            uri = (redirect_uri or "").strip()
            if not uri:
                return False
            defaults = {
                "http://127.0.0.1:5174/login/callback",
                "http://localhost:5174/login/callback",
            }
            extra = os.environ.get("BORA_GITHUB_WEB_REDIRECT_URIS") or ""
            for part in extra.split(","):
                p = part.strip()
                if p:
                    defaults.add(p)
            return uri in defaults

        def _purge_stale_oauth_states(self) -> None:
            now_ts = time.time()
            dead = [
                k
                for k, v in state.oauth_web_states.items()
                if now_ts - float(v.get("created_at") or 0) > 600
            ]
            for k in dead:
                state.oauth_web_states.pop(k, None)

        def _issue_registry_session(self, identity: Any) -> dict[str, Any] | None:
            """Allowlist check + mint Registry API token. None if not allowed (response sent)."""
            allow = state.github_login_allowlist
            login = str(getattr(identity, "login", "") or "")
            if not allow:
                _json_response(
                    self,
                    403,
                    {
                        "error": "login_not_allowed",
                        "message": (
                            "BORA_GITHUB_LOGIN_ALLOWLIST is empty; "
                            "set comma-separated GitHub logins before login"
                        ),
                    },
                )
                return None
            if login.casefold() not in {u.casefold() for u in allow}:
                _json_response(
                    self,
                    403,
                    {
                        "error": "login_not_allowed",
                        "message": (
                            f"GitHub user {login!r} is not on "
                            "BORA_GITHUB_LOGIN_ALLOWLIST "
                            f"(allowed: {', '.join(sorted(allow))})"
                        ),
                    },
                )
                return None
            api_token = secrets.token_urlsafe(32)
            state.tokens.add(
                api_token,
                DEFAULT_LOGIN_SCOPES,
                github_user=login,
            )
            display_name = getattr(identity, "name", None) or ""
            avatar_url = getattr(identity, "avatar_url", None) or ""
            github_id = getattr(identity, "id", None)
            try:
                upsert = getattr(state.meta, "upsert_user_profile", None)
                if callable(upsert):
                    upsert(
                        user_id=login,
                        display_name=str(display_name or ""),
                        avatar_url=str(avatar_url or ""),
                        github_id="" if github_id is None else str(github_id),
                    )
            except Exception:  # noqa: BLE001
                pass
            payload: dict[str, Any] = {
                "token": api_token,
                "token_type": "bearer",
                "scopes": sorted(DEFAULT_LOGIN_SCOPES),
                "github_user": login,
            }
            if github_id is not None:
                payload["github_id"] = github_id
            if display_name:
                payload["github_name"] = str(display_name)
            if avatar_url:
                payload["avatar_url"] = str(avatar_url)
            return payload

        def _auth_web_start(self) -> None:
            """Hub SPA: start Authorization Code flow (Harbor-style browser login)."""
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
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad JSON"})
                return
            redirect_uri = str(body.get("redirect_uri") or "").strip()
            if not self._allowed_web_redirect(redirect_uri):
                _json_response(
                    self,
                    400,
                    {
                        "error": "invalid_redirect_uri",
                        "message": (
                            "redirect_uri not allowed "
                            "(default: http://127.0.0.1:5174/login/callback; "
                            "extend via BORA_GITHUB_WEB_REDIRECT_URIS)"
                        ),
                    },
                )
                return
            self._purge_stale_oauth_states()
            state_token = secrets.token_urlsafe(24)
            state.oauth_web_states[state_token] = {
                "redirect_uri": redirect_uri,
                "created_at": time.time(),
            }
            sys.stderr.write(
                f"oauth web start state={state_token[:8]}... "
                f"redirect={redirect_uri!r} pending={len(state.oauth_web_states)}\n"
            )
            url = build_web_authorize_url(
                client_id=state.github_client_id,
                redirect_uri=redirect_uri,
                state=state_token,
            )
            _json_response(
                self,
                200,
                {"authorize_url": url, "state": state_token},
            )

        def _auth_web_callback(self) -> None:
            """Hub SPA: exchange GitHub code for Registry API token."""
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
            code = str(body.get("code") or "").strip()
            state_token = str(body.get("state") or "").strip()
            redirect_uri = str(body.get("redirect_uri") or "").strip()
            if not code or not state_token:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": "code and state required"},
                )
                return
            self._purge_stale_oauth_states()
            # Peek first; pop only after GitHub exchange succeeds so a double
            # client call (React StrictMode) is less likely to hit invalid_state
            # before the first exchange finishes.
            pending = state.oauth_web_states.get(state_token)
            if pending is None:
                _json_response(
                    self,
                    400,
                    {
                        "error": "invalid_state",
                        "message": "unknown or expired OAuth state; start login again",
                    },
                )
                return
            expected_redirect = str(pending.get("redirect_uri") or "")
            if redirect_uri and redirect_uri != expected_redirect:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_redirect_uri", "message": "redirect_uri mismatch"},
                )
                return
            redirect_uri = expected_redirect
            try:
                gh_token = exchange_web_code(
                    client_id=state.github_client_id,
                    client_secret=state.github_client_secret,
                    code=code,
                    redirect_uri=redirect_uri,
                )
                identity = fetch_user(gh_token)
            except GitHubOAuthError as exc:
                sys.stderr.write(f"oauth web callback failed code={exc.code} msg={exc.message!r}\n")
                _json_response(self, 400, {"error": exc.code, "message": exc.message})
                return
            state.oauth_web_states.pop(state_token, None)
            sys.stderr.write(
                f"oauth web authorized github_user={identity.login!r} (issuing registry token)\n"
            )
            payload = self._issue_registry_session(identity)
            if payload is None:
                return
            _json_response(self, 200, payload)

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
            from services.registry.oauth_github import _device_verify_url

            payload = {
                "device_code": dc.device_code,
                "user_code": dc.user_code,
                "verification_uri": dc.verification_uri,
                "expires_in": dc.expires_in,
                "interval": dc.interval,
                # One-click prefill; always re-normalize (user_code + skip picker).
                "verification_uri_complete": _device_verify_url(
                    dc.verification_uri_complete or dc.verification_uri,
                    dc.user_code,
                ),
            }
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
                sys.stderr.write(f"oauth poll github_error code={exc.code} msg={exc.message!r}\n")
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
                sys.stderr.write(f"oauth fetch_user failed code={exc.code} msg={exc.message!r}\n")
                _json_response(self, 502, {"error": exc.code, "message": exc.message})
                return
            sys.stderr.write(
                f"oauth poll authorized github_user={identity.login!r} (issuing registry token)\n"
            )
            payload = self._issue_registry_session(identity)
            if payload is None:
                return
            _json_response(self, 200, payload)

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

        def _list_packages(self, *, auth: TokenInfo, qs: dict[str, list[str]]) -> None:
            try:
                payload = state.packages.list_packages(
                    auth=auth,
                    prefix=(qs.get("database_id_prefix") or [None])[0],
                    visibility=(qs.get("visibility") or [None])[0],
                    version=(qs.get("version") or [None])[0],
                    package_kind=(qs.get("package_kind") or [None])[0],
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
                payload = state.results.list_suites(
                    auth=auth,
                    database_id=(qs.get("database_id") or [None])[0],
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
            if not auth.scopes:
                _json_response(self, 401, {"error": "unauthorized", "message": "login required"})
                return
            if not auth.user_id:
                _json_response(
                    self,
                    401,
                    {"error": "unauthorized", "message": "user identity required"},
                )
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad JSON"})
                return
            name = str(body.get("name") or "").strip().casefold()
            display_name = str(body.get("display_name") or name)
            is_claimable = bool(body.get("is_claimable", False))
            if not name or not _ORG_NAME_RE.match(name):
                _json_response(
                    self,
                    400,
                    {
                        "error": "invalid_request",
                        "message": "name must be lowercase slug [a-z0-9][a-z0-9_-]*",
                    },
                )
                return
            try:
                org = state.meta.create_org(
                    name=name,
                    owner_user_id=auth.user_id,
                    display_name=display_name,
                    is_claimable=is_claimable,
                )
            except ValueError:
                _json_response(self, 409, {"error": "conflict", "message": "org already exists"})
                return
            _json_response(self, 201, org_to_dict(org))

        def _list_orgs(self, *, auth: TokenInfo) -> None:
            if not auth.user_id:
                _json_response(self, 401, {"error": "unauthorized", "message": "login required"})
                return
            items = []
            for org, role in state.meta.list_orgs_for_user(auth.user_id):
                d = org_to_dict(org)
                d["role"] = role
                items.append(d)
            _json_response(self, 200, {"items": items})

        def _get_org(self, *, org_id: str, auth: TokenInfo) -> None:
            org = state.meta.get_org(org_id.casefold())
            if org is None:
                _json_response(self, 404, {"error": "not_found", "message": "org not found"})
                return
            # Public metadata of org is readable; membership list is restricted.
            payload = org_to_dict(org)
            if auth.user_id:
                m = state.meta.membership(org.org_id, auth.user_id)
                if m:
                    payload["role"] = m.role
            _json_response(self, 200, payload)

        def _claim_org(self, *, org_id: str, auth: TokenInfo) -> None:
            if not auth.user_id:
                _json_response(
                    self,
                    401,
                    {"error": "unauthorized", "message": "user identity required"},
                )
                return
            try:
                org = state.meta.claim_org(org_id.casefold(), auth.user_id)
            except LookupError:
                _json_response(self, 404, {"error": "not_found", "message": "org not found"})
                return
            except PermissionError as exc:
                _json_response(self, 403, {"error": "forbidden", "message": str(exc)})
                return
            _json_response(self, 200, org_to_dict(org))

        def _require_org_owner(self, *, org_id: str, auth: TokenInfo) -> bool:
            """Return True if caller may manage org (owner or admin). Sends error response if not."""
            status = state.access.org_owner_status(org_id=org_id, auth=auth)
            if status == "ok":
                return True
            if status == "not_found":
                _json_response(self, 404, {"error": "not_found", "message": "org not found"})
            elif status == "unauthorized":
                _json_response(self, 401, {"error": "unauthorized", "message": "login required"})
            else:
                _json_response(
                    self,
                    403,
                    {"error": "forbidden", "message": "owner required"},
                )
            return False

        def _create_invite_key(self, *, org_id: str, auth: TokenInfo) -> None:
            org_id = org_id.casefold()
            if not self._require_org_owner(org_id=org_id, auth=auth):
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad JSON"})
                return
            max_uses: int | None = None
            if body.get("max_uses") is not None and body.get("max_uses") != "":
                try:
                    max_uses = int(body["max_uses"])
                except (TypeError, ValueError):
                    _json_response(
                        self,
                        400,
                        {"error": "invalid_request", "message": "max_uses must be int"},
                    )
                    return
            expires_at: float | None = None
            if body.get("expires_at") is not None and body.get("expires_at") != "":
                try:
                    expires_at = float(body["expires_at"])
                except (TypeError, ValueError):
                    _json_response(
                        self,
                        400,
                        {
                            "error": "invalid_request",
                            "message": "expires_at must be unix timestamp",
                        },
                    )
                    return
            if expires_at is not None and expires_at <= now():
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": "expires_at must be in the future"},
                )
                return
            # days convenience: expires_in_days
            if expires_at is None and body.get("expires_in_days") is not None:
                try:
                    days = float(body["expires_in_days"])
                    if days <= 0:
                        raise ValueError("non-positive")
                    expires_at = now() + days * 86400.0
                except (TypeError, ValueError):
                    _json_response(
                        self,
                        400,
                        {
                            "error": "invalid_request",
                            "message": "expires_in_days must be positive number",
                        },
                    )
                    return
            # Plaintext is returned once on create; store only hash + prefix.
            plain = f"bora-inv_{secrets.token_urlsafe(24)}"
            token_hash = hashlib.sha256(plain.encode("utf-8")).hexdigest()
            prefix = plain[:16] + "…"
            try:
                row = state.meta.create_invite_key(
                    org_id=org_id,
                    created_by=auth.user_id or "",
                    token_hash=token_hash,
                    token_prefix=prefix,
                    max_uses=max_uses,
                    expires_at=expires_at,
                )
            except LookupError:
                _json_response(self, 404, {"error": "not_found", "message": "org not found"})
                return
            except ValueError as exc:
                _json_response(self, 400, {"error": "invalid_request", "message": str(exc)})
                return
            _json_response(self, 201, invite_key_to_dict(row, invite_key=plain))

        def _list_invite_keys(self, *, org_id: str, auth: TokenInfo) -> None:
            org_id = org_id.casefold()
            if not self._require_org_owner(org_id=org_id, auth=auth):
                return
            items = [invite_key_to_dict(r) for r in state.meta.list_invite_keys(org_id)]
            _json_response(self, 200, {"org_id": org_id, "items": items})

        def _revoke_invite_key(self, *, org_id: str, key_id: str, auth: TokenInfo) -> None:
            org_id = org_id.casefold()
            if not self._require_org_owner(org_id=org_id, auth=auth):
                return
            try:
                row = state.meta.revoke_invite_key(org_id, key_id)
            except LookupError:
                _json_response(self, 404, {"error": "not_found", "message": "invite key not found"})
                return
            _json_response(self, 200, invite_key_to_dict(row))

        def _join_org_with_invite(self, *, auth: TokenInfo) -> None:
            if not auth.user_id:
                _json_response(
                    self,
                    401,
                    {"error": "unauthorized", "message": "user identity required"},
                )
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad JSON"})
                return
            invite = str(body.get("invite_key") or "").strip()
            if not invite:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": "invite_key required"},
                )
                return
            token_hash = hashlib.sha256(invite.encode("utf-8")).hexdigest()
            try:
                org, mem = state.meta.redeem_invite_key(token_hash=token_hash, user_id=auth.user_id)
            except LookupError:
                _json_response(
                    self,
                    404,
                    {"error": "not_found", "message": "invalid invite key"},
                )
                return
            except PermissionError as exc:
                _json_response(self, 403, {"error": "forbidden", "message": str(exc)})
                return
            except ValueError as exc:
                _json_response(self, 409, {"error": "conflict", "message": str(exc)})
                return
            payload = org_to_dict(org)
            payload["role"] = mem.role
            payload["membership"] = membership_to_dict(mem)
            _json_response(self, 200, payload)

        def _list_org_members(self, *, org_id: str, auth: TokenInfo) -> None:
            org_id = org_id.casefold()
            org = state.meta.get_org(org_id)
            if org is None:
                _json_response(self, 404, {"error": "not_found", "message": "org not found"})
                return
            if not _is_admin(auth.scopes):
                if not auth.user_id or state.meta.membership(org_id, auth.user_id) is None:
                    _json_response(self, 404, {"error": "not_found", "message": "org not found"})
                    return
            member_rows = state.meta.list_members(org_id)
            profiles = state.meta.get_user_profiles([m.user_id for m in member_rows])
            members = [membership_to_dict(m, profile=profiles.get(m.user_id)) for m in member_rows]
            _json_response(self, 200, {"org_id": org_id, "items": members})

        def _add_org_member(self, *, org_id: str, auth: TokenInfo) -> None:
            org_id = org_id.casefold()
            if not auth.user_id and not _is_admin(auth.scopes):
                _json_response(self, 401, {"error": "unauthorized", "message": "login required"})
                return
            mem = state.meta.membership(org_id, auth.user_id) if auth.user_id else None
            if not _is_admin(auth.scopes) and (mem is None or mem.role != "owner"):
                _json_response(
                    self,
                    403,
                    {"error": "forbidden", "message": "owner required to add members"},
                )
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                _json_response(self, 400, {"error": "invalid_request", "message": "bad JSON"})
                return
            user_id = _normalize_user_id(str(body.get("user_id") or ""))
            role = str(body.get("role") or "member")
            if not user_id:
                _json_response(
                    self,
                    400,
                    {"error": "invalid_request", "message": "user_id required"},
                )
                return
            try:
                m = state.meta.add_member(org_id, user_id, role=role)
            except LookupError:
                _json_response(self, 404, {"error": "not_found", "message": "org not found"})
                return
            except ValueError as exc:
                code = "conflict" if "exists" in str(exc) else "invalid_request"
                status = 409 if code == "conflict" else 400
                _json_response(self, status, {"error": code, "message": str(exc)})
                return
            _json_response(self, 201, membership_to_dict(m))

        def _remove_org_member(self, *, org_id: str, user_id: str, auth: TokenInfo) -> None:
            org_id = org_id.casefold()
            target = _normalize_user_id(user_id) or user_id.casefold()
            mem = state.meta.membership(org_id, auth.user_id) if auth.user_id else None
            if not _is_admin(auth.scopes) and (mem is None or mem.role != "owner"):
                _json_response(
                    self,
                    403,
                    {"error": "forbidden", "message": "owner required to remove members"},
                )
                return
            try:
                state.meta.remove_member(org_id, target)
            except LookupError:
                _json_response(self, 404, {"error": "not_found", "message": "membership not found"})
                return
            _json_response(self, 200, {"ok": True, "org_id": org_id, "user_id": target})

        def _leave_org(self, *, org_id: str, auth: TokenInfo) -> None:
            org_id = org_id.casefold()
            if not auth.user_id:
                _json_response(
                    self,
                    401,
                    {"error": "unauthorized", "message": "user identity required"},
                )
                return
            try:
                state.meta.leave_org(org_id, auth.user_id)
            except LookupError:
                _json_response(
                    self,
                    404,
                    {"error": "not_found", "message": "membership not found"},
                )
                return
            except PermissionError as exc:
                _json_response(self, 403, {"error": "forbidden", "message": str(exc)})
                return
            _json_response(self, 200, {"ok": True, "org_id": org_id, "left": True})

        def _delete_org(self, *, org_id: str, auth: TokenInfo) -> None:
            org_id = org_id.casefold()
            if not self._require_org_owner(org_id=org_id, auth=auth):
                return
            try:
                state.meta.delete_org(org_id)
            except LookupError:
                _json_response(self, 404, {"error": "not_found", "message": "org not found"})
                return
            except ValueError as exc:
                _json_response(self, 409, {"error": "conflict", "message": str(exc)})
                return
            _json_response(self, 200, {"ok": True, "org_id": org_id, "dissolved": True})

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
