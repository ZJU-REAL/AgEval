"""Application use cases for Registry organizations."""

from __future__ import annotations

from typing import Any

from bora.config.errors import ConfigError
from bora.registry.client import RegistryError


class RegistryOrgCommands:
    def __init__(self, client_factory: Any) -> None:
        self._client_factory = client_factory

    def create_org(
        self,
        *,
        name: str,
        display_name: str | None = None,
        is_claimable: bool = False,
        registry_url: str | None = None,
    ) -> dict[str, Any]:
        client = self._client_factory(registry_url=registry_url, require_token=True)
        try:
            data = client.create_org(
                name=name,
                display_name=display_name,
                is_claimable=is_claimable,
            )
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        return {"ok": True, **data}

    def list_orgs(self, *, registry_url: str | None = None) -> dict[str, Any]:
        client = self._client_factory(registry_url=registry_url, require_token=True)
        try:
            data = client.list_orgs()
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            items = []
        return {"ok": True, "count": len(items), "items": items}

    def add_member(
        self,
        *,
        org_id: str,
        user_id: str,
        role: str = "member",
        registry_url: str | None = None,
    ) -> dict[str, Any]:
        if role not in {"owner", "member"}:
            raise ConfigError(
                "invalid_request",
                "role must be owner or member",
                location="registry",
            )
        client = self._client_factory(registry_url=registry_url, require_token=True)
        try:
            data = client.add_org_member(org_id=org_id, user_id=user_id, role=role)
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        return {"ok": True, **data}

    def remove_member(
        self,
        *,
        org_id: str,
        user_id: str,
        registry_url: str | None = None,
    ) -> dict[str, Any]:
        client = self._client_factory(registry_url=registry_url, require_token=True)
        try:
            data = client.remove_org_member(org_id=org_id, user_id=user_id)
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        return {"ok": True, **data}

    def set_member_role(
        self,
        *,
        org_id: str,
        user_id: str,
        role: str,
        registry_url: str | None = None,
    ) -> dict[str, Any]:
        if role not in {"owner", "member"}:
            raise ConfigError(
                "invalid_request",
                "role must be owner or member",
                location="registry",
            )
        client = self._client_factory(registry_url=registry_url, require_token=True)
        try:
            data = client.set_org_member_role(org_id=org_id, user_id=user_id, role=role)
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        return {"ok": True, **data}

    def transfer(
        self,
        *,
        org_id: str,
        user_id: str,
        registry_url: str | None = None,
    ) -> dict[str, Any]:
        client = self._client_factory(registry_url=registry_url, require_token=True)
        try:
            data = client.transfer_org(org_id=org_id, user_id=user_id)
        except RegistryError as exc:
            raise ConfigError(exc.code, exc.message, location="registry") from exc
        return {"ok": True, **data}
