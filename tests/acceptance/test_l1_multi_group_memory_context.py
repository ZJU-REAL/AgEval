"""Lock + topology public summary for container-per-group memory path."""

from __future__ import annotations

from pathlib import Path

from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw
from bora.provider.isolation import parse_logical_topology
from bora.provider.targets import IsolationMode

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "examples" / "l1" / "tasks" / "multi-agent-container-per-group"


def test_per_group_topology_two_targets_logical() -> None:
    lock = ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        TASK,
        "multi-agent-container-per-group",
        capabilities=DeclarationCapabilityCatalog(),
    )
    provider = thaw(lock.provider)
    topo = parse_logical_topology(
        provider, profile_ids={p["id"] for p in thaw(lock.agent_profiles)}
    )
    assert topo is not None
    assert topo.mode == IsolationMode.CONTAINER_PER_GROUP
    assert len(topo.groups) == 2
    assert {a.actor_id for a in topo.actors} == {"planner", "worker"}
    # No shared_write across groups in this package.
    for a in topo.actors:
        assert a.shared_write == ()
