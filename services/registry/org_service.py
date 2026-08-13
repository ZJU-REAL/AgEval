"""Org / members / invites."""

from __future__ import annotations

from typing import Any

from services.registry.access import AccessPolicy


class OrgService:
    def __init__(self, meta: Any, access: AccessPolicy) -> None:
        self.meta = meta
        self.access = access

    def get(self, org_id: str) -> Any:
        return self.meta.get_org(org_id)

    def owner_status(self, org_id: str, auth: Any) -> str:
        return self.access.org_owner_status(org_id=org_id, auth=auth)
