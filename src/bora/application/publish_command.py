"""Application use case for ``bora publish``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
from bora.registry.archive import MEDIA_TYPE, build_archive
from bora.registry.client import RegistryClient, RegistryError
from bora.registry.credentials import load_credentials
from bora.registry.digest import compute_package_digest


def publish_database(
    database_root: Path,
    *,
    public: bool = False,
    org: str | None = None,
    registry_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Validate Database, compute digests, publish to Registry; return summary dict."""
    root = database_root.expanduser().resolve(strict=False)
    try:
        manifest = load_database_manifest(root)
    except ConfigError:
        raise

    package_digest = compute_package_digest(root)
    archive, blob_digest, size = build_archive(root)

    creds = load_credentials()
    url = (registry_url or creds.url or "").rstrip("/")
    tok = token if token is not None else creds.token
    if not url:
        raise ConfigError(
            "registry_unavailable",
            "registry URL required (BORA_REGISTRY_URL or ~/.bora/credentials)",
            location="registry",
        )
    if not tok:
        raise ConfigError(
            "unauthorized",
            "registry token required (credentials file or BORA_REGISTRY_TOKEN)",
            location="registry",
        )

    client = RegistryClient(url, token=tok)
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
        "ref": f"{info.database_id}@{info.version}",
        "digest_ref": f"{info.database_id}@{info.package_digest}",
        "org_id": info.org_id or org_id,
    }
