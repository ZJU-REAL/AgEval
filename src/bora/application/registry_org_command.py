"""Application use cases for Registry organizations."""

from __future__ import annotations

import os
from typing import Any

from bora.config.errors import ConfigError
from bora.registry.client import RegistryClient, RegistryError
from bora.registry.credentials import load_credentials


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
    if not token:
        raise ConfigError(
            "unauthorized",
            "registry token required (bora login or BORA_REGISTRY_TOKEN)",
            location="registry",
        )
    return RegistryClient(url, token=token)


def create_org(
    *,
    name: str,
    display_name: str | None = None,
    is_claimable: bool = False,
    registry_url: str | None = None,
) -> dict[str, Any]:
    client = _client(registry_url=registry_url)
    try:
        data = client.create_org(
            name=name,
            display_name=display_name,
            is_claimable=is_claimable,
        )
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc
    return {"ok": True, **data}


def list_orgs(*, registry_url: str | None = None) -> dict[str, Any]:
    client = _client(registry_url=registry_url)
    try:
        data = client.list_orgs()
    except RegistryError as exc:
        raise ConfigError(exc.code, exc.message, location="registry") from exc
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        items = []
    return {"ok": True, "count": len(items), "items": items}
