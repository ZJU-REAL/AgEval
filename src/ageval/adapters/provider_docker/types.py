"""Docker L1 runtime types and Attempt-private actor UID bases."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ageval.provider.targets import TargetLedger
from ageval.runtime.identity import AttemptIdentity

# Base numeric UID for Attempt-private actors (non-root, non-host-identity claim).
_ACTOR_UID_BASE = 12000
_SHARED_GID_BASE = 13000


@dataclass
class DockerImageLock:
    kind: str
    platform: str
    image_tag: str
    image_digest: str
    build_input_digest: str

    @classmethod
    def load(cls, path: Path) -> DockerImageLock:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            kind=str(data["kind"]),
            platform=str(data["platform"]),
            image_tag=str(data.get("image_tag", "")),
            image_digest=str(data["image_digest"]),
            build_input_digest=str(data["build_input_digest"]),
        )


@dataclass
class DockerRuntime:
    attempt: AttemptIdentity
    container_id: str | None = None
    network_id: str | None = None
    image_lock: DockerImageLock | None = None
    workdir_host: Path | None = None
    package_host: Path | None = None
    cleaned: bool = False
    writer_stop_confirmed: bool = False
    termination_actions: list[str] = field(default_factory=list)
    assurance: str = "l0"  # default honest; only upgrade after full L1 workload
    policy_digests: dict[str, str] = field(default_factory=dict)
    writer_inventory: list[str] = field(default_factory=list)
    writer_stops: list[bool] = field(default_factory=list)
    # Multi-actor L1 private ledger (handles never exposed publicly).
    target_ledger: TargetLedger | None = None
    agent_container_ids: list[str] = field(default_factory=list)

    def register_writer(self, name: str) -> None:
        self.writer_inventory.append(name)

    def record_writer_stop(self, confirmed: bool) -> None:
        self.writer_stops.append(confirmed)
        self.writer_stop_confirmed = all(self.writer_stops) if self.writer_stops else False
