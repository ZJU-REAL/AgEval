"""Application use cases for registry list/show and local cache inspection."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ageval.config.errors import ConfigError
from ageval.registry.cache import PackageCache, default_cache_root
from ageval.registry.client import RegistryError
from ageval.registry.ref import parse_package_ref


class RegistryListCommands:
    def __init__(self, client_factory: Any) -> None:
        self._client_factory = client_factory

    def list_packages(
        self,
        *,
        database_id_prefix: str | None = None,
        visibility: str | None = None,
        registry_url: str | None = None,
    ) -> dict[str, Any]:
        client = self._client_factory(registry_url=registry_url, require_token=False)
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

    def show_package(self, ref: str, *, registry_url: str | None = None) -> dict[str, Any]:
        """Show metadata for ``database_id@version`` or ``database_id@sha256:…``."""
        parsed = parse_package_ref(ref)
        if parsed.kind == "path" or not parsed.database_id:
            raise ConfigError(
                "invalid_package",
                "expected database_id@version or @sha256:…",
                location=ref,
            )
        client = self._client_factory(registry_url=registry_url, require_token=False)
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

    def delete_package_release(
        self, ref: str, *, registry_url: str | None = None
    ) -> dict[str, Any]:
        """Delete a package release (org owner / admin). *ref* = database_id@version."""
        parsed = parse_package_ref(ref)
        if parsed.kind == "path" or not parsed.database_id or not parsed.version:
            raise ConfigError(
                "invalid_package",
                "expected database_id@version",
                location=ref,
            )
        if parsed.package_digest:
            raise ConfigError(
                "invalid_package",
                "delete requires database_id@version (not digest ref)",
                location=ref,
            )
        client = self._client_factory(registry_url=registry_url, require_token=False)
        try:
            return client.delete_package_release(
                database_id=parsed.database_id,
                version=parsed.version,
            )
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc

    def set_package_visibility(
        self,
        ref: str,
        *,
        visibility: str,
        registry_url: str | None = None,
    ) -> dict[str, Any]:
        """Set package release visibility (org owner / admin). *ref* = database_id@version."""
        if visibility not in {"public", "private"}:
            raise ConfigError(
                "invalid_request",
                "visibility must be public or private",
                location="registry",
            )
        parsed = parse_package_ref(ref)
        if parsed.kind == "path" or not parsed.database_id or not parsed.version:
            raise ConfigError(
                "invalid_package",
                "expected database_id@version",
                location=ref,
            )
        if parsed.package_digest:
            raise ConfigError(
                "invalid_package",
                "set-visibility requires database_id@version (not digest ref)",
                location=ref,
            )
        client = self._client_factory(registry_url=registry_url, require_token=False)
        try:
            data = client.set_package_visibility(
                database_id=parsed.database_id,
                version=parsed.version,
                visibility=visibility,
            )
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        return {"ok": True, **data}

    def cache_list(self, *, cache_root: Path | None = None) -> dict[str, Any]:
        root = (cache_root or default_cache_root()).resolve()
        base = root / "databases"
        items: list[dict[str, Any]] = []
        if base.is_dir():
            for db_dir in sorted(base.rglob(".ageval-verified")):
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

    def cache_path(self, ref: str, *, cache_root: Path | None = None) -> dict[str, Any]:
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
            listed = self.cache_list(cache_root=cache_root)
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
        self,
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
        info = self.cache_path(target, cache_root=cache_root)
        path = Path(str(info["path"]))
        if path.exists():
            shutil.rmtree(path)
        return {"ok": True, "purged": str(path), "cache_root": str(root)}
