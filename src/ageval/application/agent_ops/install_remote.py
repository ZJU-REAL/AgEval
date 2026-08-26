"""Install an agent from a local path or the Registry into the agents cache."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ageval.agents.manifest import load_agent_manifest
from ageval.agents.paths import package_dir
from ageval.agents.reserved import reject_reserved_harness_id
from ageval.agents.store import AgentIndexEntry, install_from_path
from ageval.application.agent_ops.install_plugins import install_declared_plugins
from ageval.config.errors import ConfigError
from ageval.plugins.install import InstalledItem
from ageval.registry.archive import extract_archive
from ageval.registry.client import RegistryError
from ageval.registry.media_types import AGENT_MEDIA_TYPE

HubFetch = Callable[[str], Path]


class AgentInstallCommand:
    def __init__(
        self,
        client_factory: Any,
        *,
        hub_fetch: HubFetch | None = None,
        cleanup_plugin_tmp: Callable[[], None] | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._hub_fetch = hub_fetch
        self._cleanup_plugin_tmp = cleanup_plugin_tmp
        self._tmp_dirs: list[tempfile.TemporaryDirectory[str]] = []

    def install_agent_from_path(self, source: Path) -> dict[str, Any]:
        """Copy a local agent package, then install declared plugins."""
        entry = install_from_path(source)
        try:
            plugins = self._install_plugins(entry)
        finally:
            self.cleanup_tmp()
        return _summary(entry, plugins=plugins)

    def install_agent_from_registry(
        self,
        locator: str,
        *,
        registry_url: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Locator forms: ``org/agent_id@version`` or ``org/agent_id@sha256:…``."""
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
        reject_reserved_harness_id(package_id)

        client = self._client_factory(
            registry_url=registry_url,
            token=token,
            require_token=True,
        )
        try:
            extract_dir = self._download_agent(
                client,
                package_id=package_id,
                version=None if ver_or_digest.startswith("sha256:") else ver_or_digest,
                package_digest=ver_or_digest if ver_or_digest.startswith("sha256:") else None,
                location=locator,
            )
            entry = install_from_path(extract_dir, agent_id=package_id)
            plugins = self._install_plugins(entry)
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        finally:
            self.cleanup_tmp()
        summary = _summary(entry, plugins=plugins)
        summary["from"] = locator
        return summary

    def _download_agent(
        self,
        client: Any,
        *,
        package_id: str,
        version: str | None,
        package_digest: str | None,
        location: str,
    ) -> Path:
        try:
            if package_digest:
                meta = client.get_metadata(dataset_id=package_id, package_digest=package_digest)
            else:
                meta = client.get_metadata(dataset_id=package_id, version=version)
            if meta.media_type != AGENT_MEDIA_TYPE:
                raise ConfigError(
                    "invalid_package_kind",
                    f"release is not an agent (media_type={meta.media_type})",
                    location=location,
                )
            tmp = tempfile.TemporaryDirectory(prefix="ageval-agent-dl-")
            self._tmp_dirs.append(tmp)
            archive_path = Path(tmp.name) / "agent.tar.gz"
            client.fetch_content(
                dataset_id=package_id,
                package_digest=meta.package_digest,
                dest=archive_path,
            )
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        extract_dir = Path(tmp.name) / "pkg"
        extract_dir.mkdir()
        extract_archive(archive_path, extract_dir)
        archive_path.unlink(missing_ok=True)
        return extract_dir

    def _install_plugins(self, entry: AgentIndexEntry) -> list[InstalledItem]:
        root = package_dir(entry.agent_id, entry.version)
        manifest = load_agent_manifest(root)
        return install_declared_plugins(
            manifest.binding,
            agent_root=root,
            hub_fetch=self._hub_fetch,
        )

    def cleanup_tmp(self) -> None:
        while self._tmp_dirs:
            tmp = self._tmp_dirs.pop()
            tmp.cleanup()
        if self._cleanup_plugin_tmp is not None:
            self._cleanup_plugin_tmp()


def _summary(entry: AgentIndexEntry, *, plugins: list[InstalledItem]) -> dict[str, Any]:
    summary = entry.as_dict()
    summary["ok"] = True
    summary["ref"] = f"{entry.agent_id}@{entry.version}"
    summary["plugins"] = [
        {
            "plugin_id": item.plugin_id,
            "version": item.version,
            "digest": item.digest,
            "status": item.status,
        }
        for item in plugins
    ]
    return summary
