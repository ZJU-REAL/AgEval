"""Attempt + suite result upload / list / share / delete."""

from __future__ import annotations

from typing import Any

from services.registry.access import AccessPolicy


class ResultService:
    def __init__(self, meta: Any, access: AccessPolicy) -> None:
        self.meta = meta
        self.access = access

    def get_attempt(self, run_id: str) -> Any:
        return self.meta.get_attempt(run_id)

    def get_suite(self, suite_run_id: str) -> Any:
        return self.meta.get_suite(suite_run_id)

    def can_manage(self, result_kind: str, result_id: str, auth: Any) -> bool:
        return self.access.can_manage_result(result_kind, result_id, auth, for_read=False)
