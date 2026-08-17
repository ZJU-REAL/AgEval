"""Agent identity for Hub Runtime plaza (derived; not a stored object).

Plaza unit is the agent product (ACP ``options.entry``, else plugin executor).
Transport ``acp``, model, credentials, label, role, and team are not identity.
Digest is independent of suite ``config_fingerprint``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from bora.config.digest import canonical_json_bytes
from bora.config.profiles import (
    acp_entry_from_binding,
    plugin_row_options,
    secret_free_options,
)

_TOKEN_SPLIT = re.compile(r"[-_]+")
_TRANSPORT = "acp"


def resolve_agent_id(binding: Mapping[str, Any] | None) -> str:
    """Product id: ACP extension-row ``entry``, else non-transport executor.

    Empty when the binding is transport-only ``acp`` (no entry). Does not read
    profile-level ``options.entry`` — same contract as ``acp_entry_from_binding``.
    """
    raw = binding if isinstance(binding, Mapping) else {}
    executor = str(raw.get("executor") or "").strip()
    if executor == _TRANSPORT:
        return acp_entry_from_binding(raw) or ""
    return executor


def project_harness(binding: Mapping[str, Any] | None) -> dict[str, Any]:
    """Canonical plaza object: the agent product only."""
    return {"agent": resolve_agent_id(binding)}


def harness_fingerprint(binding: Mapping[str, Any] | None) -> str:
    """Stable plaza id: ``rt_`` + first 16 hex of sha256(canonical agent)."""
    agent = resolve_agent_id(binding)
    if not agent:
        return ""
    digest = hashlib.sha256(canonical_json_bytes(project_harness(binding))).hexdigest()
    return f"rt_{digest[:16]}"


def harness_display_name(binding: Mapping[str, Any] | None) -> str:
    """Same agent axis as Hub/Viewer ``agent_label``.

    Binding ``label`` is kept as written. Otherwise humanize the agent id.
    Never name a card after transport ``acp``.
    """
    raw = binding if isinstance(binding, Mapping) else {}
    label = raw.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    agent = resolve_agent_id(raw)
    stem = _humanize(agent) if agent else ""
    return stem or "Runtime"


def runtime_refs_from_overlay(overlay: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """Per-role plaza refs from ``job_overlay.bindings``. Empty if none."""
    if not isinstance(overlay, Mapping):
        return []
    bindings = overlay.get("bindings")
    if not isinstance(bindings, Mapping):
        return []
    refs: list[dict[str, str]] = []
    for role, raw in bindings.items():
        if not isinstance(raw, Mapping):
            continue
        role_id = str(role).strip()
        rid = harness_fingerprint(raw)
        if not role_id or not rid:
            continue
        refs.append(
            {
                "role": role_id,
                "runtime_id": rid,
                "display_name": harness_display_name(raw),
            }
        )
    return refs


def binding_options(binding: Mapping[str, Any] | None) -> dict[str, Any]:
    """Secret-free executor-plugin row options (not the shared profile bag)."""
    raw = binding if isinstance(binding, Mapping) else {}
    executor = str(raw.get("executor") or "").strip()
    if not executor:
        return {}
    return secret_free_options(plugin_row_options(raw, executor))


def _humanize(stem: str) -> str:
    tokens = [part for part in _TOKEN_SPLIT.split(stem.strip()) if part]
    return " ".join(token[:1].upper() + token[1:] for token in tokens)
