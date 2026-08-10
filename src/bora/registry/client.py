"""HTTP(S) JSON client for the Database Registry service."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote


class RegistryError(Exception):
    """Operator-facing registry client failure."""

    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    database_id: str
    version: str
    visibility: str
    package_digest: str
    blob_digest: str
    size: int
    media_type: str
    org_id: str | None = None


class RegistryClient:
    """Thin HTTP client. Never receives S3 credentials — only Registry API."""

    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self, *, content_type: str | None = None, auth: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> tuple[int, bytes, dict[str, str]]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers=headers or self._headers(auth=auth),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                raw = resp.read()
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                return int(resp.status), raw, hdrs
        except urllib.error.HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                payload = {}
            code = str(payload.get("error") or "registry_http_error")
            msg = str(payload.get("message") or exc.reason or "HTTP error")
            # private concealment: 404 for unauthorized private
            raise RegistryError(code, msg, status=int(exc.code)) from exc
        except urllib.error.URLError as exc:
            raise RegistryError(
                "registry_unavailable",
                f"cannot reach registry: {exc.reason}",
            ) from exc

    def health(self) -> dict[str, Any]:
        status, raw, _ = self._request("GET", "/health", auth=False)
        if status != 200:
            raise RegistryError("registry_unavailable", f"health status {status}", status=status)
        return json.loads(raw.decode("utf-8"))

    def publish(
        self,
        *,
        database_id: str,
        version: str,
        package_digest: str,
        blob_digest: str,
        size: int,
        media_type: str,
        visibility: str,
        archive: bytes,
        org_id: str,
    ) -> ReleaseInfo:
        meta = {
            "database_id": database_id,
            "version": version,
            "package_digest": package_digest,
            "blob_digest": blob_digest,
            "size": size,
            "media_type": media_type,
            "visibility": visibility,
            "org_id": org_id,
        }
        import secrets as _secrets

        boundary = f"bora-{_secrets.token_hex(12)}"
        body = b""
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="metadata"\r\n'
        body += b"Content-Type: application/json\r\n\r\n"
        body += json.dumps(meta, sort_keys=True).encode("utf-8")
        body += b"\r\n"
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="archive"; filename="package.tar.gz"\r\n'
        body += b"Content-Type: application/octet-stream\r\n\r\n"
        body += archive
        body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        headers = self._headers(
            content_type=f"multipart/form-data; boundary={boundary}",
            auth=True,
        )
        status, raw, _ = self._request("POST", "/v1/packages", body=body, headers=headers)
        if status not in {200, 201}:
            raise RegistryError("publish_failed", f"unexpected status {status}", status=status)
        data = json.loads(raw.decode("utf-8"))
        return ReleaseInfo(
            database_id=str(data["database_id"]),
            version=str(data["version"]),
            visibility=str(data["visibility"]),
            package_digest=str(data["package_digest"]),
            blob_digest=str(data["blob_digest"]),
            size=int(data["size"]),
            media_type=str(data["media_type"]),
            org_id=str(data["org_id"]) if data.get("org_id") else None,
        )

    def get_metadata(
        self,
        *,
        database_id: str,
        version: str | None = None,
        package_digest: str | None = None,
    ) -> ReleaseInfo:
        if package_digest:
            dig = quote(package_digest, safe=":")
            path = f"/v1/packages/{quote(database_id, safe='/')}/by-digest/{dig}"
        elif version:
            ver = quote(version, safe="")
            path = f"/v1/packages/{quote(database_id, safe='/')}/versions/{ver}"
        else:
            raise RegistryError("invalid_ref", "version or package_digest required")
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("not_found", f"release not found ({status})", status=status)
        data = json.loads(raw.decode("utf-8"))
        return ReleaseInfo(
            database_id=str(data["database_id"]),
            version=str(data["version"]),
            visibility=str(data["visibility"]),
            package_digest=str(data["package_digest"]),
            blob_digest=str(data["blob_digest"]),
            size=int(data["size"]),
            media_type=str(data["media_type"]),
            org_id=str(data["org_id"]) if data.get("org_id") else None,
        )

    def fetch_content(self, *, database_id: str, package_digest: str) -> bytes:
        path = (
            f"/v1/packages/{quote(database_id, safe='/')}"
            f"/by-digest/{quote(package_digest, safe=':')}/content"
        )
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("not_found", f"content not found ({status})", status=status)
        return raw

    def list_package_files(
        self,
        *,
        database_id: str,
        package_digest: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """List package archive paths (Hub S2 / #38). Prefer immutable digest."""
        base = f"/v1/packages/{quote(database_id, safe='/')}"
        if package_digest:
            path = f"{base}/by-digest/{quote(package_digest, safe=':')}/files"
        elif version:
            path = f"{base}/versions/{quote(version, safe='')}/files"
        else:
            raise RegistryError("invalid_ref", "version or package_digest required")
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("not_found", f"files not found ({status})", status=status)
        return json.loads(raw.decode("utf-8"))

    def get_package_file(
        self,
        *,
        database_id: str,
        file_path: str,
        package_digest: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Read one package file as JSON envelope (utf-8 or base64)."""
        base = f"/v1/packages/{quote(database_id, safe='/')}"
        # Keep path segments; encode each for URL safety without collapsing slashes.
        encoded_file = "/".join(quote(seg, safe="") for seg in file_path.split("/"))
        if package_digest:
            path = f"{base}/by-digest/{quote(package_digest, safe=':')}/files/{encoded_file}"
        elif version:
            path = f"{base}/versions/{quote(version, safe='')}/files/{encoded_file}"
        else:
            raise RegistryError("invalid_ref", "version or package_digest required")
        status, raw, _ = self._request("GET", path, auth=True)
        if status == 413:
            raise RegistryError(
                "payload_too_large",
                f"file too large ({status})",
                status=status,
            )
        if status != 200:
            raise RegistryError("not_found", f"file not found ({status})", status=status)
        return json.loads(raw.decode("utf-8"))

    def list_packages(
        self,
        *,
        database_id_prefix: str | None = None,
        visibility: str | None = None,
        version: str | None = None,
    ) -> list[ReleaseInfo]:
        from urllib.parse import urlencode

        q: dict[str, str] = {}
        if database_id_prefix:
            q["database_id_prefix"] = database_id_prefix
        if visibility:
            q["visibility"] = visibility
        if version:
            q["version"] = version
        path = "/v1/packages"
        if q:
            path = f"{path}?{urlencode(q)}"
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("list_failed", f"status {status}", status=status)
        data = json.loads(raw.decode("utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise RegistryError("list_failed", "invalid list response")
        return [self._release_from_dict(item) for item in items]

    def list_package_versions(self, database_id: str) -> list[ReleaseInfo]:
        path = f"/v1/packages/{quote(database_id, safe='/')}"
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("list_failed", f"status {status}", status=status)
        data = json.loads(raw.decode("utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise RegistryError("list_failed", "invalid list response")
        return [self._release_from_dict(item) for item in items]

    def device_code(self) -> dict[str, Any]:
        status, raw, _ = self._request(
            "POST",
            "/v1/auth/github/device/code",
            body=b"{}",
            headers=self._headers(content_type="application/json", auth=False),
            auth=False,
        )
        if status != 200:
            raise RegistryError("oauth_failed", f"device code status {status}", status=status)
        return json.loads(raw.decode("utf-8"))

    def device_poll(self, device_code: str) -> dict[str, Any]:
        body = json.dumps({"device_code": device_code}).encode("utf-8")
        status, raw, _ = self._request(
            "POST",
            "/v1/auth/github/device/poll",
            body=body,
            headers=self._headers(content_type="application/json", auth=False),
            auth=False,
        )
        if status == 202:
            return {"status": "authorization_pending"}
        if status != 200:
            raise RegistryError("oauth_failed", f"poll status {status}", status=status)
        return json.loads(raw.decode("utf-8"))

    def upload_attempt(
        self,
        *,
        run_id: str,
        database_id: str,
        task_id: str,
        lock_digest: str,
        status: str,
        visibility: str,
        blob_digest: str,
        size: int,
        archive: bytes,
        suite_run_id: str | None = None,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "run_id": run_id,
            "database_id": database_id,
            "task_id": task_id,
            "lock_digest": lock_digest,
            "status": status,
            "visibility": visibility,
            "blob_digest": blob_digest,
            "size": size,
        }
        if suite_run_id:
            meta["suite_run_id"] = suite_run_id
        import secrets as _secrets

        boundary = f"bora-result-{_secrets.token_hex(12)}"
        body = b""
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="metadata"\r\n'
        body += b"Content-Type: application/json\r\n\r\n"
        body += json.dumps(meta, sort_keys=True).encode("utf-8")
        body += b"\r\n"
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="archive"; filename="attempt.tar.gz"\r\n'
        body += b"Content-Type: application/octet-stream\r\n\r\n"
        body += archive
        body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        headers = self._headers(
            content_type=f"multipart/form-data; boundary={boundary}",
            auth=True,
        )
        http_status, raw, _ = self._request(
            "POST", "/v1/results/attempts", body=body, headers=headers
        )
        if http_status not in {200, 201}:
            raise RegistryError(
                "upload_failed", f"unexpected status {http_status}", status=http_status
            )
        return json.loads(raw.decode("utf-8"))

    def get_attempt(self, run_id: str) -> dict[str, Any]:
        path = f"/v1/results/attempts/{quote(run_id, safe='')}"
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("not_found", f"attempt not found ({status})", status=status)
        return json.loads(raw.decode("utf-8"))

    def fetch_attempt_content(self, run_id: str) -> bytes:
        path = f"/v1/results/attempts/{quote(run_id, safe='')}/content"
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("not_found", f"content not found ({status})", status=status)
        return raw

    def list_attempts(self, *, database_id: str | None = None) -> list[dict[str, Any]]:
        from urllib.parse import urlencode

        path = "/v1/results/attempts"
        if database_id:
            path = f"{path}?{urlencode({'database_id': database_id})}"
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("list_failed", f"status {status}", status=status)
        data = json.loads(raw.decode("utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise RegistryError("list_failed", "invalid list response")
        return [item for item in items if isinstance(item, dict)]

    def upload_suite(
        self,
        *,
        suite_run_id: str,
        database_id: str,
        database_version: str,
        visibility: str,
        pass_rate: float,
        mean_score: float,
        metrics: dict[str, Any],
        task_refs: list[dict[str, Any]],
        agent_label: str,
        model_label: str,
        exit_code: int,
        blob_digest: str,
        size: int,
        archive: bytes,
        config_fingerprint: str | None = None,
        config_homogeneous: bool | None = None,
        actors_summary: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "suite_run_id": suite_run_id,
            "database_id": database_id,
            "database_version": database_version,
            "visibility": visibility,
            "pass_rate": pass_rate,
            "mean_score": mean_score,
            "metrics": metrics,
            "task_refs": task_refs,
            "agent_label": agent_label,
            "model_label": model_label,
            "exit_code": exit_code,
            "blob_digest": blob_digest,
            "size": size,
        }
        # #42 Leaderboard comparability — thin projection from suite summary.
        if config_fingerprint is not None:
            meta["config_fingerprint"] = config_fingerprint
        if config_homogeneous is not None:
            meta["config_homogeneous"] = config_homogeneous
        if actors_summary is not None:
            meta["actors_summary"] = actors_summary
        import secrets as _secrets

        boundary = f"bora-suite-{_secrets.token_hex(12)}"
        body = b""
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="metadata"\r\n'
        body += b"Content-Type: application/json\r\n\r\n"
        body += json.dumps(meta, sort_keys=True).encode("utf-8")
        body += b"\r\n"
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="archive"; filename="suite.tar.gz"\r\n'
        body += b"Content-Type: application/octet-stream\r\n\r\n"
        body += archive
        body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        headers = self._headers(
            content_type=f"multipart/form-data; boundary={boundary}",
            auth=True,
        )
        http_status, raw, _ = self._request(
            "POST", "/v1/results/suites", body=body, headers=headers
        )
        if http_status not in {200, 201}:
            raise RegistryError(
                "upload_failed", f"unexpected status {http_status}", status=http_status
            )
        return json.loads(raw.decode("utf-8"))

    def get_suite(self, suite_run_id: str) -> dict[str, Any]:
        path = f"/v1/results/suites/{quote(suite_run_id, safe='')}"
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("not_found", f"suite not found ({status})", status=status)
        return json.loads(raw.decode("utf-8"))

    def fetch_suite_content(self, suite_run_id: str) -> bytes:
        path = f"/v1/results/suites/{quote(suite_run_id, safe='')}/content"
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("not_found", f"content not found ({status})", status=status)
        return raw

    def list_suites(self, *, database_id: str | None = None) -> list[dict[str, Any]]:
        from urllib.parse import urlencode

        path = "/v1/results/suites"
        if database_id:
            path = f"{path}?{urlencode({'database_id': database_id})}"
        status, raw, _ = self._request("GET", path, auth=True)
        if status != 200:
            raise RegistryError("list_failed", f"status {status}", status=status)
        data = json.loads(raw.decode("utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise RegistryError("list_failed", "invalid list response")
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _release_from_dict(data: Any) -> ReleaseInfo:
        if not isinstance(data, dict):
            raise RegistryError("list_failed", "invalid release item")
        return ReleaseInfo(
            database_id=str(data["database_id"]),
            version=str(data["version"]),
            visibility=str(data["visibility"]),
            package_digest=str(data["package_digest"]),
            blob_digest=str(data["blob_digest"]),
            size=int(data["size"]),
            media_type=str(data["media_type"]),
            org_id=str(data["org_id"]) if data.get("org_id") else None,
        )

    # ---- orgs / shares ---------------------------------------------------

    def create_org(
        self,
        *,
        name: str,
        display_name: str | None = None,
        is_claimable: bool = False,
    ) -> dict[str, Any]:
        body = {
            "name": name,
            "display_name": display_name or name,
            "is_claimable": is_claimable,
        }
        status, raw, _ = self._request(
            "POST",
            "/v1/orgs",
            body=json.dumps(body, sort_keys=True).encode("utf-8"),
            headers=self._headers(content_type="application/json"),
        )
        if status not in {200, 201}:
            raise RegistryError("org_create_failed", f"status {status}", status=status)
        return json.loads(raw.decode("utf-8"))

    def list_orgs(self) -> dict[str, Any]:
        status, raw, _ = self._request("GET", "/v1/orgs")
        if status != 200:
            raise RegistryError("org_list_failed", f"status {status}", status=status)
        return json.loads(raw.decode("utf-8"))

    def add_org_member(self, *, org_id: str, user_id: str, role: str = "member") -> dict[str, Any]:
        body = {"user_id": user_id, "role": role}
        status, raw, _ = self._request(
            "POST",
            f"/v1/orgs/{quote(org_id, safe='')}/members",
            body=json.dumps(body, sort_keys=True).encode("utf-8"),
            headers=self._headers(content_type="application/json"),
        )
        if status not in {200, 201}:
            raise RegistryError("org_member_failed", f"status {status}", status=status)
        return json.loads(raw.decode("utf-8"))

    def share_result(
        self,
        *,
        result_kind: str,
        result_id: str,
        target_type: str,
        target_id: str,
    ) -> dict[str, Any]:
        body = {"target_type": target_type, "target_id": target_id}
        # result_kind is attempt|suite → attempts|suites
        kind_path = "attempts" if result_kind == "attempt" else "suites"
        path = f"/v1/results/{kind_path}/{quote(result_id, safe='')}/shares"
        status, raw, _ = self._request(
            "POST",
            path,
            body=json.dumps(body, sort_keys=True).encode("utf-8"),
            headers=self._headers(content_type="application/json"),
        )
        if status not in {200, 201}:
            raise RegistryError("share_failed", f"status {status}", status=status)
        return json.loads(raw.decode("utf-8"))

    def unshare_result(
        self,
        *,
        result_kind: str,
        result_id: str,
        target_type: str,
        target_id: str,
    ) -> dict[str, Any]:
        body = {"target_type": target_type, "target_id": target_id}
        kind_path = "attempts" if result_kind == "attempt" else "suites"
        path = f"/v1/results/{kind_path}/{quote(result_id, safe='')}/shares"
        status, raw, _ = self._request(
            "DELETE",
            path,
            body=json.dumps(body, sort_keys=True).encode("utf-8"),
            headers=self._headers(content_type="application/json"),
        )
        if status != 200:
            raise RegistryError("unshare_failed", f"status {status}", status=status)
        return json.loads(raw.decode("utf-8"))
