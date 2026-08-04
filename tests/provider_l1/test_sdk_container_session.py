"""Unit: ContainerCLIExecutor fails closed on dead/generation mismatch."""

from __future__ import annotations

from bora.adapters.agent_container import ContainerCLIExecutor
from bora.provider.targets import ActorPhysicalBinding, ExecutionTarget


def _binding(**kw):
    base = dict(
        actor_id="a1",
        group_id="g1",
        target_id="tgt_1",
        uid=12000,
        gid=12000,
        home_container="/actor-homes/a1",
        generation=1,
    )
    base.update(kw)
    return ActorPhysicalBinding(**base)


def test_target_dead_fail_closed() -> None:
    target = ExecutionTarget(
        target_id="tgt_1",
        group_id="g1",
        generation=1,
        container_id=None,
        state="dead",
    )
    ex = ContainerCLIExecutor(
        kind="codex",
        model="m",
        container_id="",
        actor=_binding(),
        target=target,
        env={},
    )
    r = ex.invoke("hi")
    assert r.ok is False
    assert r.error == "target_dead"


def test_generation_mismatch_fail_closed() -> None:
    target = ExecutionTarget(
        target_id="tgt_1",
        group_id="g1",
        generation=2,
        container_id="cid",
        state="ready",
    )
    ex = ContainerCLIExecutor(
        kind="codex",
        model="m",
        container_id="cid",
        actor=_binding(generation=1),
        target=target,
        env={},
    )
    r = ex.invoke("hi")
    assert r.ok is False
    assert r.error == "generation_mismatch"


def test_unsupported_executor_kind() -> None:
    target = ExecutionTarget(
        target_id="tgt_1",
        group_id="g1",
        generation=1,
        container_id="cid",
        state="ready",
    )
    ex = ContainerCLIExecutor(
        kind="not-a-real-cli",
        model="m",
        container_id="cid",
        actor=_binding(),
        target=target,
        env={},
    )
    r = ex.invoke("hi")
    assert r.ok is False
    assert r.error == "unsupported_capability"
