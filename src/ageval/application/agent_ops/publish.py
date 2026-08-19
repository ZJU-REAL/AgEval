"""Publish a ageval.agent/1 package to the Registry (design/14)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ageval.agents.manifest import load_agent_manifest
from ageval.config.errors import ConfigError
from ageval.registry.agent_package import (
    AGENT_MEDIA_TYPE,
    build_agent_archive,
    compute_agent_digest,
)
from ageval.registry.client import RegistryError


def hub_agent_package_id(agent_id: str, *, org: str) -> str:
    """Hub address for publish: short id concatenates; namespaced must match *org*."""
    org_id = org.strip()
    if not org_id:
        raise ConfigError("org_required", "agent publish requires --org", location="registry")
    prefix, _, name = agent_id.rpartition("/")
    if not prefix:
        return f"{org_id}/{agent_id}"
    if prefix != org_id:
        raise ConfigError(
            "agent_org_mismatch",
            f"agent_id prefix {prefix!r} does not match upload org {org_id!r}",
            location="agent.yaml:/agent_id",
        )
    return agent_id


class AgentPublishCommand:
    def __init__(self, client_factory: Any) -> None:
        self._client_factory = client_factory

    def publish_agent(
        self,
        agent_root: Path,
        *,
        public: bool = False,
        org: str | None = None,
        registry_url: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        root = agent_root.expanduser().resolve(strict=False)
        manifest = load_agent_manifest(root)
        package_id = hub_agent_package_id(manifest.agent_id, org=org or "")
        package_digest = compute_agent_digest(root)
        archive, blob_digest, size = build_agent_archive(root)

        visibility = "public" if public else "private"
        client = self._client_factory(
            registry_url=registry_url,
            token=token,
            require_token=True,
        )
        with tempfile.TemporaryDirectory(prefix="ageval-agent-") as tmp:
            archive_path = Path(tmp) / "agent.tar.gz"
            archive_path.write_bytes(archive)
            try:
                info = client.publish(
                    database_id=package_id,
                    version=manifest.version,
                    package_digest=package_digest,
                    blob_digest=blob_digest,
                    size=size,
                    media_type=AGENT_MEDIA_TYPE,
                    visibility=visibility,
                    archive=archive_path,
                    org_id=(org or "").strip(),
                    package_kind="agent",
                )
            except RegistryError as exc:
                raise ConfigError(exc.code, exc.message, location="registry") from exc

        return {
            "ok": True,
            "package_kind": "agent",
            "agent_id": manifest.agent_id,
            "package_id": info.database_id,
            "version": info.version,
            "visibility": info.visibility,
            "package_digest": info.package_digest,
            "blob_digest": info.blob_digest,
            "size": info.size,
            "media_type": info.media_type,
            "ref": f"{info.database_id}@{info.version}",
            "org_id": info.org_id or (org or "").strip(),
            "label": manifest.label,
        }
