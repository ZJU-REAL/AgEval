"""Application use cases for registry list/show and local cache inspection."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from bora.config.errors import ConfigError
from bora.registry.cache import PackageCache, default_cache_root
from bora.registry.client import RegistryClient, RegistryError
from bora.registry.credentials import load_credentials
from bora.registry.ref import parse_package_ref


def _client(*, registry_url: str | None = None) -> RegistryClient:
    creds = load_credentials()
    url = (registry_url or creds.url or os.environ.get("BORA_REGISTRY_URL") or "").rstrip("/")
    if not url:
        raise ConfigError(
            "registry_unavailable",
            "registry URL required (BORA_REGISTRY_URL or ~/.bora/credentials)",
            location="registry",
        )
    token = creds.token or os.environ.get("BORA_REGISTRY_TOKEN")
    return RegistryClient(url, token=token)


def list_packages(
    *,
    database_id_prefix: str | None = None,
    visibility: str | None = None,
    registry_url: str | None = None,
) -> dict[str, Any]:
    client = _client(registry_url=registry_url)
    try:
        items = client.list_packages(
            database_id_prefix=database_id_prefix,
            visibility=visibility,
        )
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc
    payload = [
        {
            "database_id": i.database_id,
            "version": i.version,
            "visibility": i.visibility,
            "package_digest": i.package_digest,
            "blob_digest": i.blob_digest,
            "size": i.size,
            "media_type": i.media_type,
        }
        for i in items
    ]
    return {"ok": True, "items": payload, "count": len(payload)}


def show_package(ref: str, *, registry_url: str | None = None) -> dict[str, Any]:
    """Show metadata for ``database_id@version`` or ``database_id@sha256:…``."""
    parsed = parse_package_ref(ref)
    if parsed.kind == "path" or not parsed.database_id:
        raise ConfigError(
            "invalid_package",
            "expected database_id@version or @sha256:…",
            location=ref,
        )
    client = _client(registry_url=registry_url)
    try:
        if parsed.package_digest:
            info = client.get_metadata(
                database_id=parsed.database_id,
                package_digest=parsed.package_digest,
            )
        else:
            info = client.get_metadata(
                database_id=parsed.database_id,
                version=parsed.version,
            )
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc
    return {
        "ok": True,
        "database_id": info.database_id,
        "version": info.version,
        "visibility": info.visibility,
        "package_digest": info.package_digest,
        "blob_digest": info.blob_digest,
        "size": info.size,
        "media_type": info.media_type,
    }


def cache_list(*, cache_root: Path | None = None) -> dict[str, Any]:
    root = (cache_root or default_cache_root()).resolve()
    base = root / "databases"
    items: list[dict[str, Any]] = []
    if base.is_dir():
        for db_dir in sorted(base.rglob(".bora-verified")):
            entry = db_dir.parent
            try:
                marker = json.loads(db_dir.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items.append(
                {
                    "path": str(entry),
                    "database_id": marker.get("database_id"),
                    "package_digest": marker.get("package_digest"),
                }
            )
    return {"ok": True, "cache_root": str(root), "items": items, "count": len(items)}


def cache_path(ref: str, *, cache_root: Path | None = None) -> dict[str, Any]:
    parsed = parse_package_ref(ref)
    if parsed.kind == "path" or not parsed.database_id:
        raise ConfigError(
            "invalid_package",
            "expected database_id@version or @sha256:…",
            location=ref,
        )
    cache = PackageCache(cache_root)
    digest = parsed.package_digest
    if not digest:
        listed = cache_list(cache_root=cache_root)
        matches = [
            i
            for i in listed["items"]
            if isinstance(i, dict) and i.get("database_id") == parsed.database_id
        ]
        if len(matches) == 1:
            path = str(matches[0]["path"])
            return {"ok": True, "path": path, "database_id": parsed.database_id}
        if not matches:
            raise ConfigError("cache_miss", "no verified entry for ref", location=ref)
        raise ConfigError(
            "cache_ambiguous",
            "multiple digests cached; use @sha256:… ref",
            location=ref,
        )
    path = cache.lookup(parsed.database_id, digest)
    if path is None:
        raise ConfigError("cache_miss", "no verified entry for ref", location=ref)
    return {
        "ok": True,
        "path": str(path),
        "database_id": parsed.database_id,
        "package_digest": digest,
    }


def cache_purge(
    target: str | None,
    *,
    yes: bool = False,
    cache_root: Path | None = None,
) -> dict[str, Any]:
    if not yes:
        raise ConfigError(
            "invalid_override",
            "cache_purge requires --yes (destructive)",
            location="cache",
        )
    root = (cache_root or default_cache_root()).resolve()
    if target is None or target == "all":
        db_root = root / "databases"
        if db_root.exists():
            shutil.rmtree(db_root)
        return {"ok": True, "purged": "all", "cache_root": str(root)}
    info = cache_path(target, cache_root=cache_root)
    path = Path(str(info["path"]))
    if path.exists():
        shutil.rmtree(path)
    return {"ok": True, "purged": str(path), "cache_root": str(root)}
