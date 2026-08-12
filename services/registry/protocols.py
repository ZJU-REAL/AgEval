"""Shared Protocols for Registry metadata / token stores.

SQLite and Postgres adapters implement these contracts. Dialect differences
(placeholder style, connection lifecycle) stay inside each adapter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from services.registry.store import (
        AttemptResultRow,
        MembershipRow,
        OrgRow,
        ReleaseRow,
        SuiteResultRow,
        TokenInfo,
    )


@runtime_checkable
class TokenStoreProtocol(Protocol):
    def hash_token(self, raw: str) -> str: ...

    def add(
        self,
        raw_token: str,
        scopes: frozenset[str] | set[str],
        *,
        github_user: str | None = None,
    ) -> None: ...

    def auth_for(self, raw_token: str | None) -> TokenInfo: ...

    def scopes_for(self, raw_token: str | None) -> frozenset[str]: ...


@runtime_checkable
class MetadataStoreProtocol(Protocol):
    """Public surface shared by SQLite and Postgres metadata stores."""

    def insert(self, row: ReleaseRow) -> None: ...

    def get_by_version(self, database_id: str, version: str) -> ReleaseRow | None: ...

    def get_by_digest(self, database_id: str, package_digest: str) -> ReleaseRow | None: ...

    def list_releases(self, *args: Any, **kwargs: Any) -> list[ReleaseRow]: ...

    def list_versions(self, database_id: str, *, include_private: bool = False) -> list[ReleaseRow]: ...

    def insert_attempt(self, row: AttemptResultRow) -> None: ...

    def get_attempt(self, run_id: str) -> AttemptResultRow | None: ...

    def list_attempts(self, *args: Any, **kwargs: Any) -> list[AttemptResultRow]: ...

    def insert_suite(self, row: SuiteResultRow) -> None: ...

    def get_suite(self, suite_run_id: str) -> SuiteResultRow | None: ...

    def list_suites(self, *args: Any, **kwargs: Any) -> list[SuiteResultRow]: ...

    def delete_attempt(self, run_id: str) -> AttemptResultRow: ...

    def delete_suite(self, suite_run_id: str) -> SuiteResultRow: ...

    def delete_release(self, database_id: str, version: str) -> ReleaseRow: ...

    def membership(self, org_id: str, user_id: str) -> MembershipRow | None: ...

    def get_org(self, org_id: str) -> OrgRow | None: ...

    def user_org_ids(self, user_id: str) -> set[str]: ...

    def result_shared_with_user(self, *args: Any, **kwargs: Any) -> bool: ...
