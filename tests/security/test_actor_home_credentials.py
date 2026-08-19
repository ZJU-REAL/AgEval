"""Actor HOME privacy claims in public binding views."""

from __future__ import annotations

from ageval.provider.targets import ActorPhysicalBinding


def test_binding_public_view_no_home_bytes() -> None:
    b = ActorPhysicalBinding(
        actor_id="planner",
        group_id="team",
        target_id="tgt_x",
        uid=12001,
        gid=12001,
        home_container="/actor-homes/planner",
        shared_write=("workspace/team",),
    )
    pub = b.public_view()
    assert pub["home_private"] is True
    assert "/actor-homes" not in str(pub)
    assert "12001" not in str(pub)
