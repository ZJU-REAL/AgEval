"""Shared Registry wire types (HTTP client + service payload shape)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """Package release metadata as returned by Registry JSON APIs."""

    dataset_id: str
    version: str
    visibility: str
    package_digest: str
    blob_digest: str
    size: int
    media_type: str
    org_id: str | None = None
    replaced: bool = False
    package_kind: str = "dataset"
    created_at: float = 0.0
    is_draft: bool = False
    slot: str | None = None

    @classmethod
    def from_payload(cls, data: dict) -> ReleaseInfo:
        return cls(
            dataset_id=str(data["dataset_id"]),
            version=str(data["version"]),
            visibility=str(data["visibility"]),
            package_digest=str(data["package_digest"]),
            blob_digest=str(data["blob_digest"]),
            size=int(data["size"]),
            media_type=str(data["media_type"]),
            org_id=str(data["org_id"]) if data.get("org_id") else None,
            replaced=bool(data.get("replaced")),
            package_kind=str(data.get("package_kind") or "dataset"),
            created_at=float(data["created_at"]) if data.get("created_at") is not None else 0.0,
            is_draft=bool(data.get("is_draft") or data.get("slot") == "draft"),
            slot=str(data["slot"]) if data.get("slot") else None,
        )
