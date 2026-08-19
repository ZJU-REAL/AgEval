"""Application use case for ``ageval publish``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ageval.config.database import load_database_manifest
from ageval.config.errors import ConfigError
from ageval.registry.archive import MEDIA_TYPE, write_archive
from ageval.registry.client import RegistryError
from ageval.registry.digest import compute_package_digest


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
        draft: bool = False,
    ) -> dict[str, Any]:
        """Validate Database, compute digests, publish to Registry; return summary dict.

        *replace* overwrites the same ``database_id@version`` for org owners only
        (blob, digests, visibility, size). Default remains conflict (409).
        *draft* writes the dataset draft slot (overwrite) instead of a release.
        """
        root = database_root.expanduser().resolve(strict=False)
        try:
            manifest = load_database_manifest(root)
        except ConfigError:
            raise

        package_digest = compute_package_digest(root)
        visibility = "public" if public else "private"
        org_id = (org or "").strip()
        if not org_id:
            raise ConfigError(
                "org_required",
                "publish requires --org (package must belong to an organization)",
                location="registry",
            )
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ageval-pub-") as tmp:
            archive_path = Path(tmp) / "package.tar.gz"
            blob_digest, size = write_archive(root, archive_path)
            client = self._client_factory(
                registry_url=registry_url,
                token=token,
                require_token=True,
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
                    archive=archive_path,
                    org_id=org_id,
                    replace=replace,
                    slot="draft" if draft else None,
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
        if info.is_draft:
            out["slot"] = "draft"
            out["is_draft"] = True
        return out

    def release_draft(
        self,
        database_id: str,
        *,
        public: bool = False,
        replace: bool = False,
        version: str | None = None,
        registry_url: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Promote the current dataset draft to an immutable release."""
        db_id = (database_id or "").strip()
        if not db_id:
            raise ConfigError("invalid_request", "database_id required", location="registry")
        client = self._client_factory(
            registry_url=registry_url,
            token=token,
            require_token=True,
        )
        visibility = "public" if public else None
        try:
            info = client.release_draft(
                database_id=db_id,
                visibility=visibility,
                replace=replace,
                version=(version or "").strip() or None,
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
            "from_draft": True,
            "org_id": info.org_id,
        }
        if info.replaced:
            out["replaced"] = True
        return out
