"""Inject a published ``agent_ref`` onto matching overlay roles (design/12, /14).

Compare uses ``_appearance_role_key`` (executor, ACP entry). Model and remaining
plugin options are run parameters and must not block attach. The write is
provenance only: it must not change fingerprint identity, lock bytes, or PASS.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ageval.agents.refs import published_agent_ref_parts
from ageval.application.suite.suite_config_fingerprint import _appearance_role_key
from ageval.config.errors import ERROR_INVALID_SCHEMA, ConfigError

_ROLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_DIGEST_SHORT_HEX = 12


class AttachAgentRefError(ConfigError):
    """Fail-closed overlay attach. Same operator shape as other Config errors."""


@dataclass(frozen=True, slots=True)
class AttachAgentResult:
    overlay: dict[str, Any]
    roles: tuple[str, ...]
    changed: bool
    agent_ref: str
    package_id: str
    version: str


def short_package_digest(digest: str) -> str:
    text = digest.strip()
    if text.startswith("sha256:"):
        return "sha256:" + text[len("sha256:") :][:_DIGEST_SHORT_HEX]
    return text[:_DIGEST_SHORT_HEX]


def format_published_agent_ref(package_id: str, version: str, digest: str = "") -> str:
    ref = f"{package_id.strip()}@{version.strip()}"
    if digest.strip():
        ref = f"{ref}+{short_package_digest(digest)}"
    return ref


def hub_agent_ref_parts(ref: object) -> tuple[str, str] | None:
    """``(package_id, version)`` from a Hub attach ref.

    Uploaded packs are ``org/name@version``. Builtin mechanism cards are
    ``pi@0.1.0`` (no slash). ``file:`` and ``local/`` stay None.
    """
    published = published_agent_ref_parts(ref)
    if published is not None:
        return published
    if not isinstance(ref, str):
        return None
    text = ref.strip()
    if not text or text.startswith("file:") or text.startswith("local/"):
        return None
    at = text.find("@")
    if at <= 0:
        return None
    package_id = text[:at]
    if "/" in package_id:
        return None
    from ageval.agents.reserved import canonical_harness_id

    hit = canonical_harness_id(package_id)
    if hit is None:
        return None
    rest = text[at + 1 :]
    plus = rest.find("+")
    version = (rest[:plus] if plus >= 0 else rest).strip()
    if not version:
        return None
    return hit, version


def load_builtin_attach(package_id: str, version: str) -> tuple[dict[str, Any], str, str] | None:
    """Shipped harness payload, or None when *package_id* is not builtin.

    Returns ``(binding, harness_id, agent_ref)``. Version must match the tree.
    """
    from ageval.agents.manifest import load_agent_manifest
    from ageval.agents.reserved import builtin_harness_root, canonical_harness_id
    from ageval.plugins.store import compute_tree_digest

    hit = canonical_harness_id(package_id)
    if hit is None:
        return None
    root = builtin_harness_root(hit)
    man = load_agent_manifest(root)
    if version.strip() != man.version:
        raise AttachAgentRefError(
            ERROR_INVALID_SCHEMA,
            f"{hit} ships as version {man.version}",
            location=package_id,
        )
    digest = compute_tree_digest(root)
    return (
        dict(man.binding),
        hit,
        format_published_agent_ref(hit, man.version, digest),
    )


def parse_published_agent_spec(spec: str) -> tuple[str | None, str, str]:
    """Split ``[role=]org/name@version`` or a builtin short id into a triple.

    ``local/`` and ``file:`` refs fail closed — they cannot create Hub provenance.
    """
    text = spec.strip()
    if not text:
        raise AttachAgentRefError(
            ERROR_INVALID_SCHEMA,
            "agent ref must not be empty",
            location="/agent",
        )
    role: str | None = None
    left, sep, rest = text.partition("=")
    if sep and _ROLE_RE.fullmatch(left.strip()) and rest.strip():
        role = left.strip()
        text = rest.strip()
    if "@" not in text:
        from ageval.agents.manifest import load_agent_manifest
        from ageval.agents.reserved import builtin_harness_root, canonical_harness_id

        hit = canonical_harness_id(text)
        if hit is None:
            raise AttachAgentRefError(
                ERROR_INVALID_SCHEMA,
                "agent ref must be org/name@version or a builtin harness id",
                location=spec,
            )
        version = load_agent_manifest(builtin_harness_root(hit)).version
        return role, hit, version
    parts = hub_agent_ref_parts(text)
    if parts is None:
        raise AttachAgentRefError(
            ERROR_INVALID_SCHEMA,
            "agent ref must be a published org/name@version or a builtin harness id",
            location=spec,
        )
    return role, parts[0], parts[1]


def inject_published_agent_ref(
    overlay: Mapping[str, Any] | None,
    *,
    published_binding: Mapping[str, Any],
    agent_ref: str,
    role: str | None = None,
) -> AttachAgentResult:
    """Copy *overlay* and set ``agent_ref`` on every role whose binding matches.

    *role* limits the write to one overlay role. Fail closed when nothing
    matches, a named role is missing, or a matching role already points at a
    different published ref. Same ref is idempotent.
    """
    parts = hub_agent_ref_parts(agent_ref)
    if parts is None:
        raise AttachAgentRefError(
            ERROR_INVALID_SCHEMA,
            "agent ref must be a published org/name@version or a builtin harness id",
            location="/agent_ref",
        )
    package_id, version = parts
    if not isinstance(published_binding, Mapping) or not published_binding:
        raise AttachAgentRefError(
            ERROR_INVALID_SCHEMA,
            "published agent binding is missing",
            location="/binding",
        )
    if not isinstance(overlay, Mapping):
        raise AttachAgentRefError(
            ERROR_INVALID_SCHEMA,
            "suite job_overlay is missing",
            location="/job_overlay",
        )
    profiles = overlay.get("agent_profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        raise AttachAgentRefError(
            ERROR_INVALID_SCHEMA,
            "suite job_overlay has no agent_profiles",
            location="/job_overlay/agent_profiles",
        )

    want_key = _appearance_role_key(published_binding)
    want_role = role.strip() if isinstance(role, str) and role.strip() else None
    if want_role is not None and want_role not in profiles:
        raise AttachAgentRefError(
            ERROR_INVALID_SCHEMA,
            f"overlay role {want_role!r} is missing",
            location=f"/job_overlay/agent_profiles/{want_role}",
        )

    new_profiles: dict[str, Any] = {}
    attached: list[str] = []
    changed = False
    for role_id, raw in profiles.items():
        rid = str(role_id)
        if not isinstance(raw, Mapping):
            new_profiles[rid] = raw
            continue
        row = dict(raw)
        if want_role is not None and rid != want_role:
            new_profiles[rid] = row
            continue
        if _appearance_role_key(row) != want_key:
            if want_role is not None:
                raise AttachAgentRefError(
                    ERROR_INVALID_SCHEMA,
                    "overlay binding does not match the published agent",
                    location=f"/job_overlay/agent_profiles/{rid}",
                )
            new_profiles[rid] = row
            continue
        existing = row.get("agent_ref")
        if isinstance(existing, str) and existing.strip() and existing.strip() != agent_ref:
            existing_parts = hub_agent_ref_parts(existing)
            if existing_parts != (package_id, version):
                raise AttachAgentRefError(
                    ERROR_INVALID_SCHEMA,
                    "overlay role already has a different agent_ref",
                    location=f"/job_overlay/agent_profiles/{rid}/agent_ref",
                )
            row["agent_ref"] = agent_ref
            changed = True
        elif not (isinstance(existing, str) and existing.strip()):
            row["agent_ref"] = agent_ref
            changed = True
        attached.append(rid)
        new_profiles[rid] = row

    if not attached:
        raise AttachAgentRefError(
            ERROR_INVALID_SCHEMA,
            "no overlay role matches the published agent binding",
            location="/job_overlay/agent_profiles",
        )

    new_overlay = {**dict(overlay), "agent_profiles": new_profiles}
    return AttachAgentResult(
        overlay=new_overlay,
        roles=tuple(attached),
        changed=changed,
        agent_ref=agent_ref,
        package_id=package_id,
        version=version,
    )
