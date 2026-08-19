"""Agent product fingerprint (``rt_*``) for suite comparability, not Hub grouping.

Identity is the agent product (ACP ``options.entry``, else plugin executor).
Transport ``acp``, model, credentials, label, role, team, overlays, and
``agent_ref`` are not this digest. Hub appearances group by published
``org/name`` instead (design/12). Independent of suite ``config_fingerprint``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from ageval.config.digest import canonical_json_bytes
from ageval.config.profiles import (
    acp_entry_from_profile,
    plugin_row_options,
    secret_free_options,
)

_TOKEN_SPLIT = re.compile(r"[-_]+")
_TRANSPORT = "acp"


def resolve_agent_id(profile: Mapping[str, Any] | None) -> str:
    """Product id: the ACP entry the profile names, else a non-transport executor.

    Empty when the profile is transport-only ``acp`` with no entry, because
    ``acp`` names how the Agent is reached, never which Agent it is.
    """
    raw = profile if isinstance(profile, Mapping) else {}
    executor = str(raw.get("executor") or "").strip()
    if executor == _TRANSPORT:
        return acp_entry_from_profile(raw) or ""
    return executor


def project_agent_identity(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    """Canonical plaza object: the agent product only."""
    return {"agent": resolve_agent_id(profile)}


def agent_fingerprint(profile: Mapping[str, Any] | None) -> str:
    """Stable plaza id: ``rt_`` + first 16 hex of sha256(canonical agent)."""
    agent = resolve_agent_id(profile)
    if not agent:
        return ""
    digest = hashlib.sha256(canonical_json_bytes(project_agent_identity(profile))).hexdigest()
    return f"rt_{digest[:16]}"


def agent_display_name(profile: Mapping[str, Any] | None) -> str:
    """Same agent axis as Hub/Viewer ``agent_label``.

    Binding ``label`` is kept as written. Otherwise humanize the agent id.
    Never name a card after transport ``acp``.
    """
    raw = profile if isinstance(profile, Mapping) else {}
    label = raw.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    agent = resolve_agent_id(raw)
    stem = _humanize(agent) if agent else ""
    return stem or "Runtime"


def runtime_refs_from_overlay(overlay: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """Per-role plaza refs from ``job_overlay.agent_profiles``. Empty if none."""
    if not isinstance(overlay, Mapping):
        return []
    profiles = overlay.get("agent_profiles")
    if not isinstance(profiles, Mapping):
        return []
    refs: list[dict[str, str]] = []
    for role, raw in profiles.items():
        if not isinstance(raw, Mapping):
            continue
        role_id = str(role).strip()
        rid = agent_fingerprint(raw)
        if not role_id or not rid:
            continue
        refs.append(
            {
                "role": role_id,
                "runtime_id": rid,
                "display_name": agent_display_name(raw),
            }
        )
    return refs


def profile_options(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    """Secret-free executor-plugin row options (not the shared profile bag)."""
    raw = profile if isinstance(profile, Mapping) else {}
    executor = str(raw.get("executor") or "").strip()
    if not executor:
        return {}
    return secret_free_options(plugin_row_options(raw, executor))


def _humanize(stem: str) -> str:
    tokens = [part for part in _TOKEN_SPLIT.split(stem.strip()) if part]
    return " ".join(token[:1].upper() + token[1:] for token in tokens)
