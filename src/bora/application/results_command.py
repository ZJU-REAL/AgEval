"""Application use cases for Attempt + Suite result upload / get / list."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
from bora.registry.client import RegistryClient, RegistryError
from bora.registry.credentials import load_credentials
from bora.registry.resolve import resolve_database_root
from bora.registry.results_archive import (
    build_attempt_archive,
    build_suite_archive,
    extract_attempt_archive,
    extract_suite_archive,
)


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


def _resolve_suite_dir(database_root: Path, suite_run_id: str) -> Path:
    root = database_root.expanduser().resolve(strict=False)
    candidate = root / ".bora" / "suite-runs" / suite_run_id
    if candidate.is_dir():
        return candidate
    raise ConfigError(
        "invalid_package",
        f"suite directory not found: {candidate}",
        location=str(candidate),
    )


def _load_suite_summary(suite_dir: Path) -> dict[str, Any]:
    path = suite_dir / "summary.json"
    if not path.is_file():
        raise ConfigError(
            "invalid_package",
            f"suite summary missing: {path}",
            location=str(path),
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(
            "invalid_package",
            f"unreadable suite summary: {exc}",
            location=str(path),
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(
            "invalid_package",
            "suite summary must be a JSON object",
            location=str(path),
        )
    return data


def _local_suite_item(summary: dict[str, Any], *, suite_dir: Path) -> dict[str, Any]:
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
    task_refs = summary.get("task_refs")
    if not isinstance(task_refs, list):
        # Derive from tasks[] if older summary without task_refs
        tasks = summary.get("tasks") if isinstance(summary.get("tasks"), list) else []
        task_refs = [
            {
                "task_id": t.get("task_id"),
                "status": t.get("status"),
                "score": t.get("score"),
                "run_id": t.get("run_id"),
            }
            for t in tasks
            if isinstance(t, dict)
        ]
    return {
        "suite_run_id": summary.get("suite_run_id") or suite_dir.name,
        "database_id": summary.get("database_id"),
        "database_version": summary.get("database_version"),
        "visibility": "local",
        "pass_rate": metrics.get("pass_rate"),
        "mean_score": metrics.get("mean_score"),
        "metrics": metrics,
        "task_refs": task_refs,
        "agent_label": summary.get("agent_label") or "",
        "model_label": summary.get("model_label") or "",
        "exit_code": summary.get("exit_code"),
        "summary_path": str(suite_dir / "summary.json"),
        "source": "local",
        "note": "per-task evaluator verdicts only; no suite-level PASS",
    }


def upload_suite_result(
    database_root: Path,
    *,
    suite_run_id: str,
    public: bool = False,
    agent_label: str = "",
    model_label: str = "",
    registry_url: str | None = None,
) -> dict[str, Any]:
    """Pack ``.bora/suite-runs/<id>`` and POST suite result to results store."""
    root = database_root.expanduser().resolve(strict=False)
    suite_dir = _resolve_suite_dir(root, suite_run_id)
    summary = _load_suite_summary(suite_dir)

    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
    task_refs = summary.get("task_refs")
    if not isinstance(task_refs, list):
        task_refs = []
    try:
        pass_rate = float(metrics.get("pass_rate", 0.0))
        mean_score = float(metrics.get("mean_score", 0.0))
    except (TypeError, ValueError):
        pass_rate = 0.0
        mean_score = 0.0
    try:
        exit_code = int(summary.get("exit_code", 0))
    except (TypeError, ValueError):
        exit_code = 0

    database_id = str(summary.get("database_id") or "")
    database_version = str(summary.get("database_version") or "")
    if not database_id:
        try:
            man = load_database_manifest(root)
            database_id = man.database_id
            database_version = database_version or man.version
        except ConfigError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConfigError("invalid_package", str(exc), location=str(root)) from exc

    archive, blob_digest, size = build_suite_archive(suite_dir, suite_run_id=suite_run_id)
    client = _client(registry_url=registry_url)
    try:
        info = client.upload_suite(
            suite_run_id=suite_run_id,
            database_id=database_id,
            database_version=database_version,
            visibility="public" if public else "private",
            pass_rate=pass_rate,
            mean_score=mean_score,
            metrics=dict(metrics),
            task_refs=[t for t in task_refs if isinstance(t, dict)],
            agent_label=agent_label or str(summary.get("agent_label") or ""),
            model_label=model_label or str(summary.get("model_label") or ""),
            exit_code=exit_code,
            blob_digest=blob_digest,
            size=size,
            archive=archive,
        )
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc

    return {
        "ok": True,
        "suite_run_id": info.get("suite_run_id", suite_run_id),
        "database_id": info.get("database_id", database_id),
        "database_version": info.get("database_version", database_version),
        "pass_rate": info.get("pass_rate", pass_rate),
        "mean_score": info.get("mean_score", mean_score),
        "metrics": info.get("metrics", metrics),
        "task_refs": info.get("task_refs", task_refs),
        "blob_digest": info.get("blob_digest", blob_digest),
        "size": info.get("size", size),
        "visibility": info.get("visibility", "private"),
        "note": info.get("note", "per-task evaluator verdicts only; no suite-level PASS"),
    }


def get_suite_result(
    suite_run_id: str,
    *,
    out_dir: Path | None = None,
    local: Path | str | None = None,
    registry_url: str | None = None,
) -> dict[str, Any]:
    """Fetch suite result meta (+ optional archive extract).

    When *local* is a Database root, read ``.bora/suite-runs/<id>/summary.json``
    without contacting the registry.
    """
    if local is not None:
        root = resolve_database_root(local)
        suite_dir = _resolve_suite_dir(root, suite_run_id)
        summary = _load_suite_summary(suite_dir)
        item = _local_suite_item(summary, suite_dir=suite_dir)
        return {"ok": True, **item}

    client = _client(registry_url=registry_url)
    try:
        meta = client.get_suite(suite_run_id)
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc

    result: dict[str, Any] = {"ok": True, "source": "registry", **meta}
    if out_dir is not None:
        try:
            archive = client.fetch_suite_content(suite_run_id)
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        dest = out_dir.expanduser().resolve(strict=False)
        suite_path = extract_suite_archive(archive, dest)
        result["out"] = str(suite_path)
    return result


def list_suite_results(
    *,
    database_id: str | None = None,
    local: Path | str | None = None,
    registry_url: str | None = None,
) -> dict[str, Any]:
    """List suite results from registry, or local ``.bora/suite-runs/`` when *local* set."""
    if local is not None:
        root = resolve_database_root(local)
        suite_root = root / ".bora" / "suite-runs"
        items: list[dict[str, Any]] = []
        if suite_root.is_dir():
            for child in sorted(suite_root.iterdir(), key=lambda p: p.name, reverse=True):
                if not child.is_dir():
                    continue
                summary_path = child / "summary.json"
                if not summary_path.is_file():
                    continue
                try:
                    summary = _load_suite_summary(child)
                except ConfigError:
                    continue
                item = _local_suite_item(summary, suite_dir=child)
                if database_id and item.get("database_id") != database_id:
                    continue
                items.append(item)
        return {"ok": True, "items": items, "count": len(items), "source": "local"}

    client = _client(registry_url=registry_url)
    try:
        items = client.list_suites(database_id=database_id)
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc
    return {"ok": True, "items": items, "count": len(items), "source": "registry"}
