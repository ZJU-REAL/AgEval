"""ExecutionTarget and logical isolation topology (L1 multi-actor).

Physical Docker handles stay private to the Provider ledger.
Public evidence may only record opaque target_id, mode, and image digest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IsolationMode(StrEnum):
    SHARED_CONTAINER = "shared-container"
    CONTAINER_PER_GROUP = "container-per-group"


@dataclass(frozen=True, slots=True)
class LogicalActor:
    actor_id: str
    group_id: str
    profiles: tuple[str, ...]
    shared_write: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LogicalGroup:
    group_id: str
    actor_ids: tuple[str, ...]
    shared_write: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LogicalIsolationTopology:
    """Lock-safe logical topology (no Docker ids / UIDs)."""

    mode: IsolationMode
    groups: tuple[LogicalGroup, ...]
    actors: tuple[LogicalActor, ...]
    network: str = "bridge"  # attempt-level for all agent targets

    def actor(self, actor_id: str) -> LogicalActor | None:
        return next((a for a in self.actors if a.actor_id == actor_id), None)

    def allowed_profile(self, actor_id: str, profile_id: str) -> bool:
        a = self.actor(actor_id)
        return a is not None and profile_id in a.profiles

    def public_summary(self) -> dict[str, Any]:
        """Evidence-safe view: no handles, no numeric UIDs."""
        return {
            "mode": self.mode.value,
            "network": self.network,
            "groups": [
                {
                    "id": g.group_id,
                    "actors": list(g.actor_ids),
                    "shared_write": list(g.shared_write),
                }
                for g in self.groups
            ],
            "actors": [
                {
                    "id": a.actor_id,
                    "group_id": a.group_id,
                    "profiles": list(a.profiles),
                }
                for a in self.actors
            ],
        }


@dataclass
class ExecutionTarget:
    """Provider-private physical target for one isolation unit (group or shared).

    Public fields: target_id, generation, group_id, state.
    Private fields: container_id, network name — never leave Provider / Parent ledger.
    """

    target_id: str
    group_id: str
    generation: int
    container_id: str | None = None  # private
    container_name: str | None = None  # private
    # Docker volume name for workspace when using real Linux perms (private).
    workspace_volume: str | None = None
    state: str = "pending"  # pending | ready | dead | cleaned
    image_digest: str = ""
    image_tag: str = ""

    def public_view(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "group_id": self.group_id,
            "generation": self.generation,
            "state": self.state,
            "image_digest": self.image_digest,
        }


@dataclass
class ActorPhysicalBinding:
    """Attempt-private actor → target + UID/GID (never in lock/evidence values)."""

    actor_id: str
    group_id: str
    target_id: str
    uid: int
    gid: int
    home_container: str  # path inside container
    shared_gid: int | None = None
    shared_write: tuple[str, ...] = ()
    generation: int = 1

    def public_view(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "group_id": self.group_id,
            "target_id": self.target_id,
            "generation": self.generation,
            "uid_class": "numeric_non_root",
            "home_private": True,
            "shared_write": list(self.shared_write),
        }


@dataclass
class TargetLedger:
    """Attempt-private mapping ledger for multi-actor L1."""

    topology: LogicalIsolationTopology
    targets: dict[str, ExecutionTarget] = field(default_factory=dict)
    actors: dict[str, ActorPhysicalBinding] = field(default_factory=dict)
    host_fallback_count: int = 0

    def public_summary(self) -> dict[str, Any]:
        return {
            "topology": self.topology.public_summary(),
            "targets": [t.public_view() for t in self.targets.values()],
            "actors": [a.public_view() for a in self.actors.values()],
            "host_fallback_count": self.host_fallback_count,
        }
