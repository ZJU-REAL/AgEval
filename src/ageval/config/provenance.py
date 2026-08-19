"""Package provenance (溯源) validation and Database→task merge (#18).

Provenance records *where a package/task came from* for fidelity audits.
It never participates in Attempt PASS and is not a quality score.
"""

from __future__ import annotations

from typing import Any

from ageval.config.errors import ERROR_INVALID_SCHEMA, ConfigError

PROVENANCE_KINDS = frozenset(
    {
        "port",
        "reimplementation",
        "wrapper",
        "original",
    }
)
REPLICATE_KINDS = frozenset({"port", "reimplementation", "wrapper"})

_ALLOWED_TOP = frozenset({"kind", "upstream", "parity"})
_ALLOWED_UPSTREAM = frozenset(
    {
        "name",
        "url",
        "ref",
        "commit",
        "task_id",
        "paper",
    }
)
_ALLOWED_PARITY = frozenset({"claims", "known_gaps"})


def validate_provenance(raw: object, *, location: str = "/provenance") -> dict[str, Any]:
    """Validate a provenance mapping; return a normalized plain dict.

    Fail closed on unknown keys / wrong types. Replicate kinds require
    ``upstream.url`` and at least one of ``upstream.ref`` / ``upstream.commit``.
    ``kind: original`` may omit ``upstream``.
    """
    if not isinstance(raw, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "provenance must be a mapping",
            location=location,
        )
    unknown = set(raw) - _ALLOWED_TOP
    if unknown:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"unknown provenance keys: {sorted(unknown)}",
            location=location,
        )

    kind = raw.get("kind")
    if not isinstance(kind, str) or not kind:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "provenance.kind is required",
            location=f"{location}/kind",
        )
    if kind not in PROVENANCE_KINDS:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"provenance.kind must be one of {sorted(PROVENANCE_KINDS)}; got {kind!r}",
            location=f"{location}/kind",
        )

    out: dict[str, Any] = {"kind": kind}

    upstream_raw = raw.get("upstream")
    if upstream_raw is not None:
        if not isinstance(upstream_raw, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "provenance.upstream must be a mapping when set",
                location=f"{location}/upstream",
            )
        unknown_u = set(upstream_raw) - _ALLOWED_UPSTREAM
        if unknown_u:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"unknown provenance.upstream keys: {sorted(unknown_u)}",
                location=f"{location}/upstream",
            )
        upstream: dict[str, Any] = {}
        for key in ("name", "url", "ref", "commit", "task_id", "paper"):
            val = upstream_raw.get(key)
            if val is None:
                continue
            if not isinstance(val, str) or not val.strip():
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    f"provenance.upstream.{key} must be a non-empty string when set",
                    location=f"{location}/upstream/{key}",
                )
            upstream[key] = val.strip()
        if upstream:
            out["upstream"] = upstream

    if kind in REPLICATE_KINDS:
        upstream_req = out.get("upstream")
        if not isinstance(upstream_req, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"provenance.kind={kind!r} requires provenance.upstream",
                location=f"{location}/upstream",
            )
        if not upstream_req.get("url"):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"provenance.kind={kind!r} requires provenance.upstream.url",
                location=f"{location}/upstream/url",
            )
        if not upstream_req.get("ref") and not upstream_req.get("commit"):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"provenance.kind={kind!r} requires provenance.upstream.ref "
                "and/or provenance.upstream.commit",
                location=f"{location}/upstream",
            )

    parity_raw = raw.get("parity")
    if parity_raw is not None:
        if not isinstance(parity_raw, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "provenance.parity must be a mapping when set",
                location=f"{location}/parity",
            )
        unknown_p = set(parity_raw) - _ALLOWED_PARITY
        if unknown_p:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"unknown provenance.parity keys: {sorted(unknown_p)}",
                location=f"{location}/parity",
            )
        parity: dict[str, Any] = {}
        for key in ("claims", "known_gaps"):
            val = parity_raw.get(key)
            if val is None:
                continue
            if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    f"provenance.parity.{key} must be a list of strings when set",
                    location=f"{location}/parity/{key}",
                )
            parity[key] = list(val)
        if parity:
            out["parity"] = parity

    return out


def merge_provenance(
    *,
    database: dict[str, Any] | None,
    task: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Task provenance fully replaces Database default when present.

    Returns None when neither layer declares provenance.
    """
    if task is not None:
        return task
    return database
