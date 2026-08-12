"""Central AccessPolicy for Registry HTTP authorization.

ACL decisions live here so handler routes cannot silently omit a helper call.
Response writing stays in the handler; this module only answers questions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from services.registry.store import ReleaseRow, TokenInfo

OrgOwnerStatus = Literal["ok", "not_found", "unauthorized", "forbidden"]


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    """Single authorization surface over a metadata store."""

    meta: Any

    @staticmethod
    def is_admin(scopes: frozenset[str]) -> bool:
        return "admin" in scopes

    def visible_package(self, row: ReleaseRow, auth: TokenInfo) -> bool:
        if row.visibility == "public":
            return True
        if self.is_admin(auth.scopes):
            return True
        if not auth.user_id or not row.org_id:
            return False
        return self.meta.membership(row.org_id, auth.user_id) is not None

    def visible_result(
        self,
        *,
        result_kind: str,
        result_id: str,
        visibility: str,
        uploaded_by: str,
        auth: TokenInfo,
    ) -> bool:
        if visibility == "public":
            return True
        if self.is_admin(auth.scopes):
            return True
        if not auth.user_id:
            return False
        if uploaded_by and uploaded_by == auth.user_id:
            return True
        orgs = self.meta.user_org_ids(auth.user_id) if auth.user_id else set()
        return self.meta.result_shared_with_user(
            result_kind=result_kind,
            result_id=result_id,
            user_id=auth.user_id,
            user_orgs=orgs,
        )

    def can_manage_package(self, row: ReleaseRow, auth: TokenInfo) -> bool:
        if self.is_admin(auth.scopes):
            return True
        if not auth.user_id or not row.org_id:
            return False
        mem = self.meta.membership(row.org_id, auth.user_id)
        return mem is not None and mem.role == "owner"

    def can_manage_result(
        self,
        result_kind: str,
        result_id: str,
        auth: TokenInfo,
        *,
        for_read: bool,
    ) -> bool:
        if result_kind == "attempt":
            row = self.meta.get_attempt(result_id)
            if row is None:
                return False
            if for_read:
                return self.visible_result(
                    result_kind="attempt",
                    result_id=row.run_id,
                    visibility=row.visibility,
                    uploaded_by=row.uploaded_by,
                    auth=auth,
                )
            return self.is_admin(auth.scopes) or (
                bool(auth.user_id) and row.uploaded_by == auth.user_id
            )
        row_s = self.meta.get_suite(result_id)
        if row_s is None:
            return False
        if for_read:
            return self.visible_result(
                result_kind="suite",
                result_id=row_s.suite_run_id,
                visibility=row_s.visibility,
                uploaded_by=row_s.uploaded_by,
                auth=auth,
            )
        return self.is_admin(auth.scopes) or (
            bool(auth.user_id) and row_s.uploaded_by == auth.user_id
        )

    def org_owner_status(self, *, org_id: str, auth: TokenInfo) -> OrgOwnerStatus:
        org = self.meta.get_org(org_id)
        if org is None:
            return "not_found"
        if self.is_admin(auth.scopes):
            return "ok"
        if not auth.user_id:
            return "unauthorized"
        mem = self.meta.membership(org_id, auth.user_id)
        if mem is None or mem.role != "owner":
            return "forbidden"
        return "ok"
