"""Attempt + suite result upload / list / share / delete."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from services.registry.access import AccessPolicy
from services.registry.errors import RegistryAppError
from services.registry.store import (
    AttemptResultRow,
    SuiteResultRow,
    TokenInfo,
    _normalize_user_id,
    _run_ids_from_tasks_json,
    attempt_to_dict,
    now,
    share_to_dict,
    suite_to_dict,
)

_SECRET_PATTERNS = (
    re.compile(rb"(?i)-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(rb"(?i)BORA_REGISTRY_TOKEN\s*="),
    re.compile(rb"(?i)github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"(?i)ghp_[A-Za-z0-9]{20,}"),
)


def _archive_looks_like_secret_leak(archive: bytes) -> bool:
    sample = archive if len(archive) < 4_000_000 else archive[:4_000_000]
    return any(p.search(sample) for p in _SECRET_PATTERNS)


class ResultService:
    def __init__(
        self,
        meta: Any,
        blobs: Any,
        access: AccessPolicy,
        *,
        max_upload: int,
    ) -> None:
        self.meta = meta
        self.blobs = blobs
        self.access = access
        self.max_upload = max_upload

    def get_attempt(self, run_id: str) -> Any:
        return self.meta.get_attempt(run_id)

    def get_suite(self, suite_run_id: str) -> Any:
        return self.meta.get_suite(suite_run_id)

    def can_manage(self, result_kind: str, result_id: str, auth: TokenInfo) -> bool:
        return self.access.can_manage_result(result_kind, result_id, auth, for_read=False)

    def upload_attempt(
        self, *, meta: dict[str, Any], archive: bytes, auth: TokenInfo
    ) -> dict[str, Any]:
        if len(archive) > self.max_upload:
            raise RegistryAppError(
                "payload_too_large",
                f"max {self.max_upload} bytes",
                http_status=413,
            )
        run_id = str(meta.get("run_id") or "")
        database_id = str(meta.get("database_id") or "")
        task_id = str(meta.get("task_id") or "")
        lock_digest = str(meta.get("lock_digest") or "")
        status = str(meta.get("status") or "")
        visibility = str(meta.get("visibility") or "private")
        blob_digest = str(meta.get("blob_digest") or "")
        size = int(meta.get("size") or len(archive))
        suite_run_id = str(meta.get("suite_run_id") or "").strip()
        if not run_id or not database_id:
            raise RegistryAppError(
                "invalid_request",
                "run_id and database_id required",
                http_status=400,
            )
        if visibility not in {"private", "public"}:
            raise RegistryAppError("invalid_request", "bad visibility", http_status=400)
        actual_blob = f"sha256:{hashlib.sha256(archive).hexdigest()}"
        if actual_blob != blob_digest or size != len(archive):
            raise RegistryAppError(
                "digest_mismatch",
                "blob digest or size mismatch",
                http_status=400,
            )
        if _archive_looks_like_secret_leak(archive):
            raise RegistryAppError(
                "secret_scan_failed",
                "archive rejected: possible credential material",
                http_status=400,
            )
        replace = bool(meta.get("replace")) or str(meta.get("replace") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        existing = self.meta.get_attempt(run_id)
        if existing is not None:
            if not replace:
                raise RegistryAppError(
                    "conflict",
                    "attempt result already exists",
                    http_status=409,
                )
            if not (
                AccessPolicy.is_admin(auth.scopes)
                or (auth.user_id and existing.uploaded_by == auth.user_id)
            ):
                raise RegistryAppError("not_found", "attempt not found", http_status=404)
            self.meta.delete_attempt(run_id)
            self._gc_attempt_blob(existing.blob_digest)
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
            uploaded_by=auth.user_id or "",
            suite_run_id=suite_run_id,
        )
        try:
            self.blobs.put_if_absent(blob_digest, archive, prefix="results")
            self.meta.insert_attempt(row)
        except ValueError as exc:
            raise RegistryAppError(
                "conflict",
                "attempt result already exists",
                http_status=409,
            ) from exc
        payload = attempt_to_dict(row)
        if existing is not None and replace:
            payload["replaced"] = True
        return payload

    def list_attempts(self, *, auth: TokenInfo, database_id: str | None) -> dict[str, Any]:
        rows = self.meta.list_attempts(database_id=database_id or None, include_private=True)
        items = [attempt_to_dict(r) for r in rows if self._visible_attempt(r, auth)]
        return {"items": items}

    def serve_attempt_meta(self, *, run_id: str, auth: TokenInfo) -> dict[str, Any]:
        return attempt_to_dict(self._require_visible_attempt(run_id, auth))

    def serve_attempt_content(
        self, *, run_id: str, auth: TokenInfo
    ) -> tuple[bytes, AttemptResultRow]:
        row = self._require_visible_attempt(run_id, auth)
        data = self.blobs.get(row.blob_digest, prefix="results")
        if data is None:
            raise RegistryAppError("not_found", "blob missing", http_status=404)
        return data, row

    def list_attempt_files(self, *, run_id: str, auth: TokenInfo) -> dict[str, Any]:
        from services.registry.package_files import get_or_build_index

        row = self._require_visible_attempt(run_id, auth)
        archive = self.blobs.get(row.blob_digest, prefix="results")
        if archive is None:
            raise RegistryAppError("not_found", "blob missing", http_status=404)
        try:
            index = get_or_build_index(archive, package_digest=row.blob_digest)
        except Exception as exc:  # noqa: BLE001
            raise RegistryAppError(
                "archive_error",
                f"cannot index attempt: {exc}",
                http_status=500,
            ) from exc
        return {
            "run_id": row.run_id,
            "database_id": row.database_id,
            "task_id": row.task_id,
            "digest": row.blob_digest,
            "items": index.list_items(),
        }

    def read_attempt_file(self, *, run_id: str, file_path: str, auth: TokenInfo) -> dict[str, Any]:
        from services.registry.package_files import (
            MAX_FILE_BYTES,
            PackageFileNotFound,
            PackageFileTooLarge,
            PackagePathError,
            file_payload,
            normalize_package_path,
            read_member,
        )

        row = self._require_visible_attempt(run_id, auth)
        try:
            safe_path = normalize_package_path(file_path)
        except PackagePathError as exc:
            raise RegistryAppError("invalid_path", str(exc), http_status=400) from exc
        archive = self.blobs.get(row.blob_digest, prefix="results")
        if archive is None:
            raise RegistryAppError("not_found", "blob missing", http_status=404)
        try:
            data, size, truncated = read_member(
                archive, safe_path, max_bytes=MAX_FILE_BYTES, allow_truncate=True
            )
        except PackagePathError as exc:
            raise RegistryAppError("invalid_path", str(exc), http_status=400) from exc
        except PackageFileNotFound as exc:
            raise RegistryAppError(
                "not_found", f"file not found: {safe_path}", http_status=404
            ) from exc
        except PackageFileTooLarge as exc:
            raise RegistryAppError(
                "file_too_large",
                str(exc),
                http_status=413,
                extra={"max_bytes": MAX_FILE_BYTES, "path": exc.path, "size": exc.size},
            ) from exc
        return file_payload(safe_path, data, size=size, truncated=truncated)

    def upload_suite(
        self, *, meta: dict[str, Any], archive: bytes, auth: TokenInfo
    ) -> dict[str, Any]:
        if len(archive) > self.max_upload:
            raise RegistryAppError(
                "payload_too_large",
                f"max {self.max_upload} bytes",
                http_status=413,
            )
        suite_run_id = str(meta.get("suite_run_id") or "")
        database_id = str(meta.get("database_id") or "")
        database_version = str(meta.get("database_version") or "")
        visibility = str(meta.get("visibility") or "private")
        blob_digest = str(meta.get("blob_digest") or "")
        size = int(meta.get("size") or len(archive))
        if not suite_run_id or not database_id:
            raise RegistryAppError(
                "invalid_request",
                "suite_run_id and database_id required",
                http_status=400,
            )
        if visibility not in {"private", "public"}:
            raise RegistryAppError("invalid_request", "bad visibility", http_status=400)
        if "pass" in meta or "verdict" in meta or meta.get("suite_pass") is not None:
            raise RegistryAppError(
                "invalid_request",
                "suite-level PASS/verdict fields are not accepted",
                http_status=400,
            )
        actual_blob = f"sha256:{hashlib.sha256(archive).hexdigest()}"
        if actual_blob != blob_digest or size != len(archive):
            raise RegistryAppError(
                "digest_mismatch",
                "blob digest or size mismatch",
                http_status=400,
            )
        if _archive_looks_like_secret_leak(archive):
            raise RegistryAppError(
                "secret_scan_failed",
                "archive rejected: possible credential material",
                http_status=400,
            )
        metrics = meta.get("metrics") if isinstance(meta.get("metrics"), dict) else {}
        task_refs = meta.get("task_refs") if isinstance(meta.get("task_refs"), list) else []
        try:
            pass_rate = float(meta.get("pass_rate", metrics.get("pass_rate", 0.0)))
            mean_score = float(meta.get("mean_score", metrics.get("mean_score", 0.0)))
        except (TypeError, ValueError) as exc:
            raise RegistryAppError(
                "invalid_request",
                "pass_rate/mean_score must be numeric",
                http_status=400,
            ) from exc
        try:
            exit_code = int(meta.get("exit_code", 0))
        except (TypeError, ValueError):
            exit_code = 0
        config_payload: dict[str, Any] = {}
        if meta.get("config_fingerprint"):
            config_payload["config_fingerprint"] = str(meta["config_fingerprint"])
        if "config_homogeneous" in meta:
            config_payload["config_homogeneous"] = bool(meta.get("config_homogeneous"))
        actors_raw = meta.get("actors_summary")
        if isinstance(actors_raw, list):
            config_payload["actors_summary"] = [a for a in actors_raw if isinstance(a, dict)]
        overlay_raw = meta.get("job_overlay")
        if isinstance(overlay_raw, dict) and overlay_raw:
            config_payload["job_overlay"] = overlay_raw
        replace = bool(meta.get("replace")) or str(meta.get("replace") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        existing = self.meta.get_suite(suite_run_id)
        if existing is not None:
            if not replace:
                raise RegistryAppError(
                    "conflict",
                    "suite result already exists",
                    http_status=409,
                )
            if not (
                AccessPolicy.is_admin(auth.scopes)
                or (auth.user_id and existing.uploaded_by == auth.user_id)
            ):
                raise RegistryAppError("not_found", "suite not found", http_status=404)
            self.meta.delete_suite(suite_run_id)
            self._gc_suite_blob(existing.blob_digest)
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
            uploaded_by=auth.user_id or "",
        )
        try:
            self.blobs.put_if_absent(blob_digest, archive, prefix="suite-results")
            self.meta.insert_suite(row)
        except ValueError as exc:
            raise RegistryAppError(
                "conflict",
                "suite result already exists",
                http_status=409,
            ) from exc
        payload = suite_to_dict(row)
        if existing is not None and replace:
            payload["replaced"] = True
        return payload

    def list_suites(self, *, auth: TokenInfo, database_id: str | None) -> dict[str, Any]:
        rows = self.meta.list_suites(database_id=database_id or None, include_private=True)
        visible = [r for r in rows if self._visible_suite(r, auth)]
        attempt_ids = self._suite_visible_attempt_ids(visible, auth=auth)
        return {"items": [suite_to_dict(r, attempt_content_ids=attempt_ids) for r in visible]}

    def serve_suite_meta(self, *, suite_run_id: str, auth: TokenInfo) -> dict[str, Any]:
        row = self._require_visible_suite(suite_run_id, auth)
        attempt_ids = self._suite_visible_attempt_ids([row], auth=auth)
        return suite_to_dict(row, attempt_content_ids=attempt_ids)

    def serve_suite_content(
        self, *, suite_run_id: str, auth: TokenInfo
    ) -> tuple[bytes, SuiteResultRow]:
        row = self._require_visible_suite(suite_run_id, auth)
        data = self.blobs.get(row.blob_digest, prefix="suite-results")
        if data is None:
            raise RegistryAppError("not_found", "blob missing", http_status=404)
        return data, row

    def list_shares(self, *, result_kind: str, result_id: str, auth: TokenInfo) -> dict[str, Any]:
        if not self.access.can_manage_result(result_kind, result_id, auth, for_read=True):
            raise RegistryAppError("not_found", "result not found", http_status=404)
        shares = self.meta.list_result_shares(result_kind=result_kind, result_id=result_id)
        return {
            "result_kind": result_kind,
            "result_id": result_id,
            "items": [share_to_dict(s) for s in shares],
        }

    def add_share(
        self,
        *,
        result_kind: str,
        result_id: str,
        target_type: str,
        target_id: str,
        auth: TokenInfo,
    ) -> dict[str, Any]:
        if not self.can_manage(result_kind, result_id, auth):
            raise RegistryAppError("not_found", "result not found", http_status=404)
        target_type = target_type.strip()
        target_id = target_id.strip()
        if target_type not in {"org", "user"} or not target_id:
            raise RegistryAppError(
                "invalid_request",
                "target_type (org|user) and target_id required",
                http_status=400,
            )
        if target_type == "user":
            target_id = _normalize_user_id(target_id) or target_id.casefold()
        else:
            target_id = target_id.casefold()
            if self.meta.get_org(target_id) is None:
                raise RegistryAppError(
                    "org_not_found",
                    f"org {target_id!r} not found",
                    http_status=400,
                )
        try:
            share = self.meta.add_result_share(
                result_kind=result_kind,
                result_id=result_id,
                target_type=target_type,
                target_id=target_id,
            )
        except ValueError as exc:
            raise RegistryAppError("conflict", "share already exists", http_status=409) from exc
        return share_to_dict(share)

    def remove_share(
        self,
        *,
        result_kind: str,
        result_id: str,
        target_type: str,
        target_id: str,
        auth: TokenInfo,
    ) -> dict[str, Any]:
        if not self.can_manage(result_kind, result_id, auth):
            raise RegistryAppError("not_found", "result not found", http_status=404)
        target_type = target_type.strip()
        target_id = target_id.strip()
        if target_type == "user":
            target_id = _normalize_user_id(target_id) or target_id.casefold()
        else:
            target_id = target_id.casefold()
        try:
            self.meta.remove_result_share(
                result_kind=result_kind,
                result_id=result_id,
                target_type=target_type,
                target_id=target_id,
            )
        except LookupError as exc:
            raise RegistryAppError("not_found", "share not found", http_status=404) from exc
        return {"ok": True}

    def delete_attempt(self, *, run_id: str, auth: TokenInfo) -> dict[str, Any]:
        if not self.can_manage("attempt", run_id, auth):
            raise RegistryAppError("not_found", "attempt not found", http_status=404)
        row = self.meta.get_attempt(run_id)
        if row is None:
            raise RegistryAppError("not_found", "attempt not found", http_status=404)
        blob_deleted = self._delete_attempt_row(row)
        return {
            "ok": True,
            "result_kind": "attempt",
            "result_id": run_id,
            "blob_deleted": blob_deleted,
        }

    def delete_suite(
        self, *, suite_run_id: str, with_attempts: bool, auth: TokenInfo
    ) -> dict[str, Any]:
        if not self.can_manage("suite", suite_run_id, auth):
            raise RegistryAppError("not_found", "suite not found", http_status=404)
        row = self.meta.get_suite(suite_run_id)
        if row is None:
            raise RegistryAppError("not_found", "suite not found", http_status=404)
        deleted_attempts: list[str] = []
        skipped_attempts: list[str] = []
        if with_attempts:
            for att in self._collect_suite_linked_attempts(row):
                if not (
                    AccessPolicy.is_admin(auth.scopes)
                    or (auth.user_id and att.uploaded_by == auth.user_id)
                ):
                    skipped_attempts.append(att.run_id)
                    continue
                self._delete_attempt_row(att)
                deleted_attempts.append(att.run_id)
        self.meta.delete_suite(suite_run_id)
        blob_deleted = self._gc_suite_blob(row.blob_digest)
        payload: dict[str, Any] = {
            "ok": True,
            "result_kind": "suite",
            "result_id": suite_run_id,
            "blob_deleted": blob_deleted,
            "with_attempts": with_attempts,
            "deleted_attempts": deleted_attempts,
        }
        if skipped_attempts:
            payload["skipped_attempts"] = skipped_attempts
        return payload

    def patch_attempt(self, *, run_id: str, visibility: str, auth: TokenInfo) -> dict[str, Any]:
        if not self.can_manage("attempt", run_id, auth):
            raise RegistryAppError("not_found", "attempt not found", http_status=404)
        if visibility not in {"public", "private"}:
            raise RegistryAppError(
                "invalid_request",
                "visibility must be public or private",
                http_status=400,
            )
        try:
            row = self.meta.set_attempt_visibility(run_id, visibility)
        except LookupError as exc:
            raise RegistryAppError("not_found", "attempt not found", http_status=404) from exc
        return attempt_to_dict(row)

    def patch_suite(self, *, suite_run_id: str, visibility: str, auth: TokenInfo) -> dict[str, Any]:
        if not self.can_manage("suite", suite_run_id, auth):
            raise RegistryAppError("not_found", "suite not found", http_status=404)
        if visibility not in {"public", "private"}:
            raise RegistryAppError(
                "invalid_request",
                "visibility must be public or private",
                http_status=400,
            )
        try:
            row = self.meta.set_suite_visibility(suite_run_id, visibility)
        except LookupError as exc:
            raise RegistryAppError("not_found", "suite not found", http_status=404) from exc
        return suite_to_dict(row)

    def _visible_attempt(self, row: AttemptResultRow, auth: TokenInfo) -> bool:
        return self.access.visible_result(
            result_kind="attempt",
            result_id=row.run_id,
            visibility=row.visibility,
            uploaded_by=row.uploaded_by,
            auth=auth,
        )

    def _visible_suite(self, row: SuiteResultRow, auth: TokenInfo) -> bool:
        return self.access.visible_result(
            result_kind="suite",
            result_id=row.suite_run_id,
            visibility=row.visibility,
            uploaded_by=row.uploaded_by,
            auth=auth,
        )

    def _require_visible_attempt(self, run_id: str, auth: TokenInfo) -> AttemptResultRow:
        row = self.meta.get_attempt(run_id)
        if row is None or not self._visible_attempt(row, auth):
            raise RegistryAppError("not_found", "attempt not found", http_status=404)
        return row

    def _require_visible_suite(self, suite_run_id: str, auth: TokenInfo) -> SuiteResultRow:
        row = self.meta.get_suite(suite_run_id)
        if row is None or not self._visible_suite(row, auth):
            raise RegistryAppError("not_found", "suite not found", http_status=404)
        return row

    def _suite_visible_attempt_ids(
        self, rows: list[SuiteResultRow], *, auth: TokenInfo
    ) -> set[str]:
        run_ids: list[str] = []
        for r in rows:
            run_ids.extend(_run_ids_from_tasks_json(r.tasks_json))
        try:
            attempts = self.meta.attempts_for_ids(run_ids)
        except Exception:  # noqa: BLE001
            return set()
        return {a.run_id for a in attempts if self._visible_attempt(a, auth)}

    def _gc_attempt_blob(self, blob_digest: str) -> bool:
        if not blob_digest:
            return False
        if self.meta.count_attempt_blob_refs(blob_digest) > 0:
            return False
        return bool(self.blobs.delete(blob_digest, prefix="results"))

    def _gc_suite_blob(self, blob_digest: str) -> bool:
        if not blob_digest:
            return False
        if self.meta.count_suite_blob_refs(blob_digest) > 0:
            return False
        return bool(self.blobs.delete(blob_digest, prefix="suite-results"))

    def _delete_attempt_row(self, row: AttemptResultRow) -> bool:
        self.meta.delete_attempt(row.run_id)
        return self._gc_attempt_blob(row.blob_digest)

    def _collect_suite_linked_attempts(self, suite_row: SuiteResultRow) -> list[AttemptResultRow]:
        by_id: dict[str, AttemptResultRow] = {}
        for att in self.meta.list_attempts_for_suite(suite_row.suite_run_id):
            by_id[att.run_id] = att
        run_ids = list(_run_ids_from_tasks_json(suite_row.tasks_json))
        try:
            refs = json.loads(suite_row.tasks_json)
        except (json.JSONDecodeError, TypeError):
            refs = []
        if isinstance(refs, list):
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                extra = ref.get("attempt_run_ids")
                if isinstance(extra, list):
                    for rid in extra:
                        text = str(rid or "").strip()
                        if text:
                            run_ids.append(text)
        for att in self.meta.attempts_for_ids(run_ids):
            by_id[att.run_id] = att
        return list(by_id.values())
