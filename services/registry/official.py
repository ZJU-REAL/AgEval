"""Hub marketplace official-org policy. Not a lock/run gate."""

from __future__ import annotations

import os

DEFAULT_OFFICIAL_ORGS: tuple[str, ...] = ("Official",)
ENV_OFFICIAL_ORGS = "BORA_OFFICIAL_ORGS"


def official_orgs() -> frozenset[str]:
    raw = os.environ.get(ENV_OFFICIAL_ORGS, "").strip()
    if raw:
        return frozenset(part.strip() for part in raw.split(",") if part.strip())
    return frozenset(DEFAULT_OFFICIAL_ORGS)


def is_official_upload_org(org_id: str | None) -> bool:
    if not org_id:
        return False
    return org_id in official_orgs()
