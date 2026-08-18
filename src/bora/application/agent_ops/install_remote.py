"""Install an agent from the Registry into the local agents cache (design/14)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from bora.agents.store import AgentIndexEntry, install_from_path
from bora.config.errors import ConfigError
from bora.registry.archive import extract_archive
from bora.registry.client import RegistryError
from bora.registry.media_types import AGENT_MEDIA_TYPE


class AgentInstallCommand:
    def __init__(self, client_factory: Any) -> None:
        self._client_factory = client_factory
        self._tmp_dirs: list[tempfile.TemporaryDirectory[str]] = []

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
            entry: AgentIndexEntry = install_from_path(extract_dir, agent_id=package_id)
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        finally:
            self.cleanup_tmp()
        summary = entry.as_dict()
        summary["ok"] = True
        summary["ref"] = f"{entry.agent_id}@{entry.version}"
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
                meta = client.get_metadata(database_id=package_id, package_digest=package_digest)
            else:
                meta = client.get_metadata(database_id=package_id, version=version)
            if meta.media_type != AGENT_MEDIA_TYPE:
                raise ConfigError(
                    "invalid_package_kind",
                    f"release is not an agent (media_type={meta.media_type})",
                    location=location,
                )
            tmp = tempfile.TemporaryDirectory(prefix="bora-agent-dl-")
            self._tmp_dirs.append(tmp)
            archive_path = Path(tmp.name) / "agent.tar.gz"
            client.fetch_content(
                database_id=package_id,
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

    def cleanup_tmp(self) -> None:
        while self._tmp_dirs:
            tmp = self._tmp_dirs.pop()
            tmp.cleanup()
