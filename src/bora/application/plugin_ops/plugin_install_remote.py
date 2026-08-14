"""Install a plugin from Registry into local plugins cache (Spec 04 → Spec 03)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from bora.config.errors import ConfigError
from bora.plugins.store import install_from_path
from bora.registry.archive import extract_archive
from bora.registry.client import RegistryError
from bora.registry.plugin_package import PLUGIN_MEDIA_TYPE


class PluginInstallCommand:
    def __init__(self, client_factory: Any) -> None:
        self._client_factory = client_factory

    def install_plugin_from_registry(
        self,
        locator: str,
        *,
        registry_url: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Locator forms: ``org/plugin_id@version`` or ``org/plugin_id@sha256:…``."""
        if "@" not in locator:
            raise ConfigError(
                "invalid_ref",
                "locator must be package_id@version or package_id@sha256:…",
                location=locator,
            )
        package_id, ver_or_digest = locator.rsplit("@", 1)
        package_id = package_id.strip()
        ver_or_digest = ver_or_digest.strip()
        if not package_id or not ver_or_digest:
            raise ConfigError("invalid_ref", "empty package_id or version", location=locator)

        client = self._client_factory(
            registry_url=registry_url,
            token=token,
            require_token=True,
        )
        try:
            if ver_or_digest.startswith("sha256:"):
                meta = client.get_metadata(database_id=package_id, package_digest=ver_or_digest)
            else:
                meta = client.get_metadata(database_id=package_id, version=ver_or_digest)
            if meta.media_type != PLUGIN_MEDIA_TYPE:
                raise ConfigError(
                    "invalid_package_kind",
                    f"release is not a plugin (media_type={meta.media_type})",
                    location=locator,
                )
            archive = client.fetch_content(
                database_id=package_id, package_digest=meta.package_digest
            )
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc

        with tempfile.TemporaryDirectory(prefix="bora-plugin-") as tmp:
            extract_dir = Path(tmp) / "pkg"
            extract_dir.mkdir()
            extract_archive(archive, extract_dir)
            entry = install_from_path(extract_dir, plugin_id=package_id)
        return {
            "ok": True,
            "plugin_id": entry.plugin_id,
            "version": entry.version,
            "digest": entry.digest,
            "path": entry.path,
            "from": locator,
        }
