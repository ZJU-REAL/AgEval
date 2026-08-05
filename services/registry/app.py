"""Stdlib HTTP Database Registry service.

Endpoints:
  GET  /health
  POST /v1/packages                       (publish multipart)
  GET  /v1/packages/{id}/versions/{ver}
  GET  /v1/packages/{id}/by-digest/{dig}
  GET  /v1/packages/{id}/by-digest/{dig}/content

Scopes: registry:publish | read-private | admin
Private unauthorized → 404 (not 403).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

# Allow `python -m services.registry.app` from repo root.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from services.registry.store import (  # noqa: E402
    FilesystemBlobStore,
    MemoryBlobStore,
    MetadataStore,
    ReleaseRow,
    TokenStore,
    now,
    release_to_dict,
)

MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 64 MiB hard top for v1


class RegistryState:
    def __init__(
        self,
        *,
        meta: MetadataStore,
        blobs: FilesystemBlobStore | MemoryBlobStore,
        tokens: TokenStore,
        max_upload: int = MAX_UPLOAD_BYTES,
    ) -> None:
        self.meta = meta
        self.blobs = blobs
        self.tokens = tokens
        self.max_upload = max_upload


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _bearer(handler: BaseHTTPRequestHandler) -> str | None:
    auth = handler.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _parse_multipart(body: bytes, content_type: str) -> dict[str, bytes]:
    m = re.search(r"boundary=([^;]+)", content_type)
    if not m:
        raise ValueError("missing multipart boundary")
    boundary = m.group(1).strip().encode()
    parts = body.split(b"--" + boundary)
    out: dict[str, bytes] = {}
    for part in parts:
        if part in (b"", b"--\r\n", b"--", b"\r\n"):
            continue
        if part.startswith(b"--"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        header_blob, _, data = part.partition(b"\r\n\r\n")
        headers = header_blob.decode("utf-8", errors="replace")
        name_m = re.search(r'name="([^"]+)"', headers)
        if not name_m:
            continue
        out[name_m.group(1)] = data.rstrip(b"\r\n")
    return out


def make_handler(state: RegistryState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            # Avoid logging Authorization headers; default log is path-only enough.
            sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

        def do_GET(self) -> None:  # noqa: N802
            path = unquote(self.path.split("?", 1)[0])
            if path == "/health":
                _json_response(self, 200, {"ok": True, "service": "bora-registry"})
                return
            token = _bearer(self)
            scopes = state.tokens.scopes_for(token)

            m = re.fullmatch(
                r"/v1/packages/(.+)/versions/([^/]+)",
                path,
            )
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
            _json_response(self, 404, {"error": "not_found", "message": "unknown path"})

        def do_POST(self) -> None:  # noqa: N802
            path = unquote(self.path.split("?", 1)[0])
            if path != "/v1/packages":
                _json_response(self, 404, {"error": "not_found", "message": "unknown path"})
                return
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
                _json_response(
                    self, 400, {"error": "invalid_request", "message": "bad visibility"}
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
            # Verify packageDigest by extract + re-hash.
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
                state.blobs.put_if_absent(blob_digest, archive)
                state.meta.insert(row)
            except ValueError:
                _json_response(
                    self,
                    409,
                    {"error": "conflict", "message": "release already exists"},
                )
                return
            _json_response(self, 201, release_to_dict(row))

        def _visible(self, row: ReleaseRow, scopes: frozenset[str]) -> bool:
            if row.visibility == "public":
                return True
            return "read-private" in scopes or "admin" in scopes or "registry:publish" in scopes

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
            if row is None or not self._visible(row, scopes):
                # private concealment
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
            if row is None or not self._visible(row, scopes):
                _json_response(self, 404, {"error": "not_found", "message": "release not found"})
                return
            data = state.blobs.get(row.blob_digest)
            if data is None:
                _json_response(self, 404, {"error": "not_found", "message": "blob missing"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Bora-Blob-Digest", row.blob_digest)
            self.end_headers()
            self.wfile.write(data)

    return Handler


def build_default_state(
    data_dir: Path, *, bootstrap_token: str | None = None
) -> tuple[RegistryState, str]:
    meta = MetadataStore(data_dir / "meta.sqlite3")
    blobs = FilesystemBlobStore(data_dir / "blobs")
    tokens = TokenStore()
    token = bootstrap_token or secrets.token_urlsafe(24)
    tokens.add(token, {"registry:publish", "read-private", "admin"})
    return RegistryState(meta=meta, blobs=blobs, tokens=tokens), token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BORA Database Registry service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8700)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".bora/registry-data"),
        help="Metadata SQLite + filesystem blob root",
    )
    parser.add_argument(
        "--bootstrap-token",
        default=None,
        help="API token (default: random, printed once to stderr)",
    )
    parser.add_argument(
        "--memory-blob",
        action="store_true",
        help="Use in-memory blob store (tests only)",
    )
    args = parser.parse_args(argv)
    data_dir = args.data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    state, token = build_default_state(data_dir, bootstrap_token=args.bootstrap_token)
    if args.memory_blob:
        state = RegistryState(
            meta=state.meta,
            blobs=MemoryBlobStore(),
            tokens=state.tokens,
            max_upload=state.max_upload,
        )
    handler = make_handler(state)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    sys.stderr.write(
        f"bora-registry listening on http://{args.host}:{args.port}\n"
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
