"""Logical → physical target mapping (no raw handle in public views)."""

from __future__ import annotations

from bora.provider.isolation import parse_logical_topology
from bora.provider.targets import (
    ActorPhysicalBinding,
    ExecutionTarget,
    IsolationMode,
    TargetLedger,
)


def test_public_views_hide_handles() -> None:
    topo = parse_logical_topology(
        {
            "network": "bridge",
            "agent_isolation": {
                "mode": "container-per-group",
                "groups": [
                    {
                        "id": "g1",
                        "actors": [{"id": "a1", "profiles": ["p1"]}],
                    },
                    {
                        "id": "g2",
                        "actors": [{"id": "a2", "profiles": ["p1"]}],
                    },
                ],
            },
        },
        profile_ids={"p1"},
    )
    assert topo is not None
    assert topo.mode == IsolationMode.CONTAINER_PER_GROUP
    target = ExecutionTarget(
        target_id="tgt_abc",
        group_id="g1",
        generation=1,
        container_id="deadbeefcontainer",
        state="ready",
        image_digest="sha256:img",
    )
    pub = target.public_view()
    assert "container_id" not in pub
    assert pub["target_id"] == "tgt_abc"
    assert "deadbeef" not in str(pub)

    binding = ActorPhysicalBinding(
        actor_id="a1",
        group_id="g1",
        target_id="tgt_abc",
        uid=12000,
        gid=12000,
        home_container="/actor-homes/a1",
        generation=1,
    )
    bpub = binding.public_view()
    assert "uid" not in bpub
    assert bpub["uid_class"] == "numeric_non_root"
    assert bpub["home_private"] is True

    ledger = TargetLedger(topology=topo)
    ledger.targets["tgt_abc"] = target
    ledger.actors["a1"] = binding
    summary = ledger.public_summary()
    assert "host_fallback_count" not in summary
    assert "deadbeef" not in str(summary)
