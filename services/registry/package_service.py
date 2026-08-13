"""Package publish / list / serve / delete / patch (HTTP adapter calls this)."""

from __future__ import annotations

from typing import Any

from services.registry.access import AccessPolicy
from services.registry.store import ReleaseRow


class PackageService:
    def __init__(self, meta: Any, access: AccessPolicy) -> None:
        self.meta = meta
        self.access = access

    def get(self, database_id: str, version: str) -> ReleaseRow | None:
        return self.meta.get_by_version(database_id, version)

    def can_manage(self, row: ReleaseRow, auth: Any) -> bool:
        return self.access.can_manage_package(row, auth)
