"""Unit: ContainerCLIExecutor fails closed on dead/generation / migration."""

from __future__ import annotations

from bora.adapters.agent_container import ContainerCLIExecutor, effective_run_gid
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


def test_private_cli_invoke_refused() -> None:
    target = ExecutionTarget(
        target_id="tgt_1",
        group_id="g1",
        generation=1,
        container_id="cid",
        state="ready",
    )
    ex = ContainerCLIExecutor(
        kind="codex",
        model="m",
        container_id="cid",
        actor=_binding(),
        target=target,
        env={},
    )
    r = ex.invoke("hi")
    assert r.ok is False
    assert r.error == "migrated_to_acp"


def test_effective_run_gid_shared_write() -> None:
    actor = _binding(shared_gid=13000, shared_write=("workspace/team",))
    assert effective_run_gid(actor) == 13000
    actor2 = _binding(shared_gid=None, shared_write=())
    assert effective_run_gid(actor2) == 12000
