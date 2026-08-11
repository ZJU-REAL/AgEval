"""Immutable Config models and lock summary view.

All nested structures returned from ``load_and_lock`` are recursively frozen
(mapping → MappingProxyType, list → tuple) so consumers cannot mutate the
canonical Trial truth.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any


def freeze(value: Any) -> Any:
    """Recursively freeze mappings and sequences for immutability."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(freeze(item) for item in value)
    return value


def thaw(value: Any) -> Any:
    """Deep-copy a frozen structure into plain dict/list for canonicalization."""
    if isinstance(value, Mapping):
        return {str(k): thaw(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ResolutionEntry:
    """One effective value source in merge order."""

    source: str
    pointer: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class ResolutionRecord:
    """Ordered record of how the locked config was assembled."""

    entries: tuple[ResolutionEntry, ...] = ()

    def as_plain(self) -> list[dict[str, str]]:
        return [
            {"source": e.source, "pointer": e.pointer, **({"note": e.note} if e.note else {})}
            for e in self.entries
        ]


@dataclass(frozen=True, slots=True)
class LockedTaskConfig:
    """Immutable locked task configuration — Trial configuration truth for v0.1+."""

    format: str
    task_id: str
    harness: Mapping[str, Any]
    parameters: Mapping[str, Any]
    provider: Mapping[str, Any]
    agent_profiles: tuple[Mapping[str, Any], ...]
    environment: Mapping[str, Any] | None
    limits: Mapping[str, Any]
    artifacts: Mapping[str, Any]
    evaluation: Mapping[str, Any]
    resolution: ResolutionRecord
    digest: str
    # Package-relative resolved references (entrypoints, artifact paths, inputs).
    resolved_references: Mapping[str, Any] = field(default_factory=lambda: freeze({}))
    # Optional package provenance (溯源); observational — never Attempt PASS.
    provenance: Mapping[str, Any] | None = None
    # Secret-free job binding overlay used for this lock (#59); not task identity.
    job_overlay: Mapping[str, Any] | None = None
    # Spec 00: per-profile resolved extension point graph (constitution §7.4).
    extension_bindings: Mapping[str, Any] | None = None

    def canonical_payload(self) -> dict[str, Any]:
        """Payload used for digest: everything except the digest field itself."""
        payload: dict[str, Any] = {
            "format": self.format,
            "task_id": self.task_id,
            "harness": thaw(self.harness),
            "parameters": thaw(self.parameters),
            "provider": thaw(self.provider),
            "agent_profiles": thaw(self.agent_profiles),
            "environment": thaw(self.environment),
            "limits": thaw(self.limits),
            "artifacts": thaw(self.artifacts),
            "evaluation": thaw(self.evaluation),
            "resolution": self.resolution.as_plain(),
            "resolved_references": thaw(self.resolved_references),
        }
        if self.provenance is not None:
            payload["provenance"] = thaw(self.provenance)
        # job_overlay is derived from resolved agent_profiles binding; include so
        # digest reflects the job binding artifact operators can rehydrate.
        if self.job_overlay is not None:
            payload["job_overlay"] = thaw(self.job_overlay)
        if self.extension_bindings is not None:
            payload["extension_bindings"] = thaw(self.extension_bindings)
        return payload


@dataclass(frozen=True, slots=True)
class LockSummary:
    """Deterministic CLI stdout view (no secrets, no host absolute paths)."""

    format: str
    task_id: str
    resolved_references: Mapping[str, Any]
    resolution: Sequence[Mapping[str, str]]
    digest: str
    provenance: Mapping[str, Any] | None = None
    job_overlay: Mapping[str, Any] | None = None
    extension_bindings: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        # Always return plain JSON-serializable dict/list trees (no MappingProxy).
        out: dict[str, Any] = {
            "digest": self.digest,
            "format": self.format,
            "resolution": thaw(list(self.resolution)),
            "resolved_references": thaw(self.resolved_references),
            "task_id": self.task_id,
        }
        if self.provenance is not None:
            out["provenance"] = thaw(self.provenance)
        if self.job_overlay is not None:
            out["job_overlay"] = thaw(self.job_overlay)
        if self.extension_bindings is not None:
            out["extension_bindings"] = thaw(self.extension_bindings)
        return out


def locked_to_summary(lock: LockedTaskConfig) -> LockSummary:
    """Project a LockedTaskConfig into the public lock summary."""
    return LockSummary(
        format=lock.format,
        task_id=lock.task_id,
        resolved_references=lock.resolved_references,
        resolution=tuple(freeze(e) for e in lock.resolution.as_plain()),
        digest=lock.digest,
        provenance=lock.provenance,
        job_overlay=lock.job_overlay,
        extension_bindings=lock.extension_bindings,
    )


def model_as_dict(obj: Any) -> dict[str, Any]:
    """Helper for tests — convert frozen dataclasses when needed."""
    if hasattr(obj, "as_dict"):
        return obj.as_dict()  # type: ignore[no-any-return]
    return asdict(obj)
