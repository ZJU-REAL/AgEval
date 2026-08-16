"""Harness identity for Hub Runtime plaza (derived; not a stored object).

Identity is executor + secret-free options. Model, credentials, label, role,
and team are excluded. Digest is independent of suite ``config_fingerprint``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from bora.config.digest import canonical_json_bytes
from bora.config.profiles import display_agent_name, secret_free_options

_TOKEN_SPLIT = re.compile(r"[-_]+")


def project_harness(binding: Mapping[str, Any] | None) -> dict[str, Any]:
    """Canonical harness object: ``executor`` + secret-free ``options``."""
    raw = binding if isinstance(binding, Mapping) else {}
    executor = str(raw.get("executor") or "").strip()
    raw_options = raw.get("options") if isinstance(raw.get("options"), Mapping) else None
    options = secret_free_options(raw_options)
    return {"executor": executor, "options": options}


def harness_fingerprint(binding: Mapping[str, Any] | None) -> str:
    """Stable plaza id: ``rt_`` + first 16 hex of sha256(canonical harness)."""
    digest = hashlib.sha256(canonical_json_bytes(project_harness(binding))).hexdigest()
    return f"rt_{digest[:16]}"


def harness_display_name(binding: Mapping[str, Any] | None) -> str:
    """Humanized stem from ``display_agent_name``; no collision suffix."""
    raw = binding if isinstance(binding, Mapping) else {}
    stem = _humanize(display_agent_name(raw))
    if stem:
        return stem
    fallback = _humanize(str(raw.get("executor") or "").strip())
    return fallback or "Runtime"


def appearance_entry(binding: Mapping[str, Any] | None) -> str:
    """Card entry: ``options.entry`` or ``options.agent`` or ``executor``."""
    raw = binding if isinstance(binding, Mapping) else {}
    options = raw.get("options")
    if isinstance(options, Mapping):
        for key in ("entry", "agent"):
            val = options.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    return str(raw.get("executor") or "").strip()


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
        if not role_id:
            continue
        refs.append(
            {
                "role": role_id,
                "runtime_id": harness_fingerprint(raw),
                "display_name": harness_display_name(raw),
            }
        )
    return refs


def _humanize(stem: str) -> str:
    tokens = [part for part in _TOKEN_SPLIT.split(stem.strip()) if part]
    return " ".join(token[:1].upper() + token[1:] for token in tokens)
