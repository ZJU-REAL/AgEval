"""Hub marketplace official-org policy. Not a lock/run gate."""

from __future__ import annotations

import os

DEFAULT_OFFICIAL_ORGS: tuple[str, ...] = ("official",)
ENV_OFFICIAL_ORGS = "BORA_OFFICIAL_ORGS"


def official_orgs() -> frozenset[str]:
    raw = os.environ.get(ENV_OFFICIAL_ORGS, "").strip()
    if raw:
        return frozenset(part.strip() for part in raw.split(",") if part.strip())
    return frozenset(DEFAULT_OFFICIAL_ORGS)


def is_official_upload_org(org_id: str | None) -> bool:
    if not org_id:
        return False
    allowed = {item.casefold() for item in official_orgs()}
    return org_id.casefold() in allowed
