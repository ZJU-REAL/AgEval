"""Application use case for ``bora publish``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
from bora.registry.archive import MEDIA_TYPE, build_archive
from bora.registry.client import RegistryError
from bora.registry.digest import compute_package_digest


class PublishCommand:
    def __init__(self, client_factory: Any) -> None:
        self._client_factory = client_factory

    def publish_database(
        self,
        database_root: Path,
        *,
        public: bool = False,
        org: str | None = None,
        registry_url: str | None = None,
        token: str | None = None,
        replace: bool = False,
    ) -> dict[str, Any]:
        """Validate Database, compute digests, publish to Registry; return summary dict.

        *replace* overwrites the same ``database_id@version`` for org owners only
        (blob, digests, visibility, size). Default remains conflict (409).
        """
        root = database_root.expanduser().resolve(strict=False)
        try:
            manifest = load_database_manifest(root)
        except ConfigError:
            raise

        package_digest = compute_package_digest(root)
        archive, blob_digest, size = build_archive(root)
        client = self._client_factory(
            registry_url=registry_url,
            token=token,
            require_token=True,
        )
        visibility = "public" if public else "private"
        org_id = (org or "").strip()
        if not org_id:
            raise ConfigError(
                "org_required",
                "publish requires --org (package must belong to an organization)",
                location="registry",
            )
        try:
            info = client.publish(
                database_id=manifest.database_id,
                version=manifest.version,
                package_digest=package_digest,
                blob_digest=blob_digest,
                size=size,
                media_type=MEDIA_TYPE,
                visibility=visibility,
                archive=archive,
                org_id=org_id,
                replace=replace,
            )
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc

        out: dict[str, Any] = {
            "ok": True,
            "database_id": info.database_id,
            "version": info.version,
            "visibility": info.visibility,
            "package_digest": info.package_digest,
            "blob_digest": info.blob_digest,
            "size": info.size,
            "media_type": info.media_type,
            "ref": f"{info.database_id}@{info.version}",
            "digest_ref": f"{info.database_id}@{info.package_digest}",
            "org_id": info.org_id or org_id,
        }
        if info.replaced:
            out["replaced"] = True
        return out
