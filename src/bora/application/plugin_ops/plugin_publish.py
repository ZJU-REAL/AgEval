"""Publish a bora.plugin/1 package to the Registry (Spec 04)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bora.config.errors import ConfigError
from bora.plugins.manifest import PluginManifestError, load_manifest, require_namespaced_plugin_id
from bora.registry.client import RegistryError
from bora.registry.plugin_package import (
    PLUGIN_MEDIA_TYPE,
    build_plugin_archive,
    compute_plugin_digest,
)


class PluginPublishCommand:
    def __init__(self, client_factory: Any) -> None:
        self._client_factory = client_factory

    def publish_plugin(
        self,
        plugin_root: Path,
        *,
        public: bool = False,
        org: str | None = None,
        registry_url: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        root = plugin_root.expanduser().resolve(strict=False)
        try:
            manifest = load_manifest(root)
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(
                "invalid_plugin",
                str(exc),
                location=str(root),
            ) from exc

        org_id = (org or "").strip()
        if not org_id:
            raise ConfigError(
                "org_required",
                "plugin publish requires --org",
                location="registry",
            )
        try:
            package_id = require_namespaced_plugin_id(manifest.plugin_id, org=org_id)
        except PluginManifestError as exc:
            raise ConfigError(exc.kind, exc.message, location="plugin.yaml:/plugin_id") from exc

        package_digest = compute_plugin_digest(root)
        archive, blob_digest, size = build_plugin_archive(root)
        client = self._client_factory(
            registry_url=registry_url,
            token=token,
            require_token=True,
        )
        visibility = "public" if public else "private"
        try:
            info = client.publish(
                database_id=package_id,
                version=manifest.version,
                package_digest=package_digest,
                blob_digest=blob_digest,
                size=size,
                media_type=PLUGIN_MEDIA_TYPE,
                visibility=visibility,
                archive=archive,
                org_id=org_id,
                package_kind="plugin",
            )
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc

        return {
            "ok": True,
            "package_kind": "plugin",
            "plugin_id": manifest.plugin_id,
            "package_id": info.database_id,
            "version": info.version,
            "visibility": info.visibility,
            "package_digest": info.package_digest,
            "blob_digest": info.blob_digest,
            "size": info.size,
            "media_type": info.media_type,
            "ref": f"{info.database_id}@{info.version}",
            "org_id": info.org_id or org_id,
            "slots_summary": manifest.slots_summary(),
        }
