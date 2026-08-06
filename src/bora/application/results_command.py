"""Application use cases for Attempt result upload / get / list."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
from bora.registry.client import RegistryClient, RegistryError
from bora.registry.credentials import load_credentials
from bora.registry.results_archive import build_attempt_archive, extract_attempt_archive


def _client(*, registry_url: str | None = None) -> RegistryClient:
    creds = load_credentials()
    url = (
        registry_url
        or os.environ.get("BORA_RESULTS_URL")
        or creds.url
        or os.environ.get("BORA_REGISTRY_URL")
        or ""
    ).rstrip("/")
    if not url:
        raise ConfigError(
            "registry_unavailable",
            "registry URL required (BORA_REGISTRY_URL / BORA_RESULTS_URL or credentials)",
            location="registry",
        )
    token = creds.token or os.environ.get("BORA_REGISTRY_TOKEN")
    if not token:
        raise ConfigError(
            "unauthorized",
            "registry token required (bora login, credentials file, or BORA_REGISTRY_TOKEN)",
            location="registry",
        )
    return RegistryClient(url, token=token)


def _resolve_run_dir(database_root: Path, run_id: str) -> Path:
    root = database_root.expanduser().resolve(strict=False)
    candidate = root / ".bora" / "runs" / run_id
    if candidate.is_dir():
        return candidate
    raise ConfigError(
        "invalid_package",
        f"run directory not found: {candidate}",
        location=str(candidate),
    )


def _read_run_meta(run_dir: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for name in ("result.json", "status.json", "summary.json"):
        path = run_dir / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            meta.update(data)
    return meta


def upload_attempt_result(
    database_root: Path,
    *,
    run_id: str,
    public: bool = False,
    registry_url: str | None = None,
) -> dict[str, Any]:
    """Pack ``.bora/runs/<run_id>`` and POST to results store."""
    root = database_root.expanduser().resolve(strict=False)
    try:
        manifest = load_database_manifest(root)
        database_id = manifest.database_id
    except ConfigError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConfigError("invalid_package", str(exc), location=str(root)) from exc

    run_dir = _resolve_run_dir(root, run_id)
    archive, blob_digest, size = build_attempt_archive(run_dir, run_id=run_id)
    meta = _read_run_meta(run_dir)
    task_id = str(meta.get("task_id") or "")
    lock_digest = str(meta.get("lock_digest") or meta.get("digest") or "")
    status = str(meta.get("status") or meta.get("verdict") or meta.get("outcome") or "")

    client = _client(registry_url=registry_url)
    try:
        info = client.upload_attempt(
            run_id=run_id,
            database_id=database_id,
            task_id=task_id,
            lock_digest=lock_digest,
            status=status,
            visibility="public" if public else "private",
            blob_digest=blob_digest,
            size=size,
            archive=archive,
        )
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc

    return {
        "ok": True,
        "run_id": info.get("run_id", run_id),
        "database_id": info.get("database_id", database_id),
        "blob_digest": info.get("blob_digest", blob_digest),
        "size": info.get("size", size),
        "visibility": info.get("visibility", "private"),
        "status": info.get("status", status),
    }


def get_attempt_result(
    run_id: str,
    *,
    out_dir: Path,
    registry_url: str | None = None,
) -> dict[str, Any]:
    """Download attempt bundle and extract under *out_dir*."""
    client = _client(registry_url=registry_url)
    try:
        meta = client.get_attempt(run_id)
        archive = client.fetch_attempt_content(run_id)
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc

    dest = out_dir.expanduser().resolve(strict=False)
    run_path = extract_attempt_archive(archive, dest)
    return {
        "ok": True,
        "run_id": run_id,
        "database_id": meta.get("database_id"),
        "blob_digest": meta.get("blob_digest"),
        "out": str(run_path),
        "meta": meta,
    }


def list_attempt_results(
    *,
    database_id: str | None = None,
    registry_url: str | None = None,
) -> dict[str, Any]:
    client = _client(registry_url=registry_url)
    try:
        items = client.list_attempts(database_id=database_id)
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc
    return {"ok": True, "items": items, "count": len(items)}
