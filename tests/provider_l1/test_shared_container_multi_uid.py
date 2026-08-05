"""shared-container topology assigns distinct actor UIDs (logical prep)."""

from __future__ import annotations

from bora.provider.isolation import parse_logical_topology
from bora.provider.targets import IsolationMode


def test_shared_container_two_actors_same_group() -> None:
    topo = parse_logical_topology(
        {
            "network": "bridge",
            "agent_isolation": {
                "mode": "shared-container",
                "groups": [
                    {
                        "id": "team",
                        "actors": [
                            {"id": "planner", "profiles": ["p1"]},
                            {"id": "reviewer", "profiles": ["p2"]},
                        ],
                        "shared_write": ["workspace/team"],
                    }
                ],
            },
        },
        profile_ids={"p1", "p2"},
    )
    assert topo is not None
    assert topo.mode == IsolationMode.SHARED_CONTAINER
    assert len(topo.actors) == 2
    assert all(a.group_id == "team" for a in topo.actors)
    assert all(a.shared_write == ("workspace/team",) for a in topo.actors)


def test_container_per_group_one_target_per_group_logical() -> None:
    topo = parse_logical_topology(
        {
            "network": "bridge",
            "agent_isolation": {
                "mode": "container-per-group",
                "groups": [
                    {"id": "g1", "actors": [{"id": "a1", "profiles": ["p"]}]},
                    {"id": "g2", "actors": [{"id": "a2", "profiles": ["p"]}]},
                ],
            },
        },
        profile_ids={"p"},
    )
    assert topo is not None
    assert len(topo.groups) == 2
    assert topo.actor("a1") is not None
    assert topo.actor("a2") is not None
    assert not topo.allowed_profile("a1", "missing")
