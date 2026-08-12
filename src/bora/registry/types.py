"""Shared Registry wire types (HTTP client + service payload shape)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """Package release metadata as returned by Registry JSON APIs."""

    database_id: str
    version: str
    visibility: str
    package_digest: str
    blob_digest: str
    size: int
    media_type: str
    org_id: str | None = None
    replaced: bool = False
