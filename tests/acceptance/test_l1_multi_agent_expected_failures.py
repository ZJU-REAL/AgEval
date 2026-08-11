"""Expected-failure matrix for L1 multi-agent scheduling (Spec 18 Phase 4)."""

from __future__ import annotations

from bora.runtime.parent_agent_service import ParentAgentService, SessionBinding
from tests.helpers.extension_registry import registry_with_executor


def test_unknown_actor_open_fail_closed() -> None:
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "x", "model": "m"}],
        agent_invocation_limit=1,
        attempt_id="attempt_ef001",
        extension_registry=registry_with_executor("x", object()),
        require_actor_id=True,
        validate_actor_profile=lambda a, p: {"ok": False, "error": "unknown_actor"},
        l1_container_only=True,
    )
    r = svc.open_session(profile_id="p1", actor_id="ghost")
    assert r["ok"] is False
    assert r["error"] == "unknown_actor"


def test_profile_allowlist_violation() -> None:
    svc = ParentAgentService(
        profiles=[
            {"id": "p1", "executor": "x", "model": "m"},
            {"id": "p2", "executor": "x", "model": "m"},
        ],
        agent_invocation_limit=1,
        attempt_id="attempt_ef002",
        extension_registry=registry_with_executor("x", object()),
        require_actor_id=True,
        validate_actor_profile=lambda a, p: {"ok": False, "error": "profile_not_allowed"},
        l1_container_only=True,
    )
    r = svc.open_session(profile_id="p2", actor_id="a1")
    assert r["ok"] is False
    assert r["error"] == "profile_not_allowed"


def test_l1_host_resolve_forbidden_on_invoke() -> None:
    def validate(a: str, p: str) -> dict:
        return {"ok": True, "target_id": "tgt", "generation": 1}

    # make_target_executor missing → l1_executor_unbound (no host path exists).
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "x", "model": "m"}],
        agent_invocation_limit=1,
        attempt_id="attempt_ef003",
        extension_registry=registry_with_executor("x", object()),
        require_actor_id=True,
        validate_actor_profile=validate,
        make_target_executor=None,
        l1_container_only=True,
    )
    opened = svc.open_session(profile_id="p1", actor_id="a1")
    assert opened["ok"]
    inv = svc.invoke(session_id=opened["session_id"], prompt="x")
    assert inv["ok"] is False
    assert inv["error"] == "l1_executor_unbound"


def test_generation_mismatch_via_executor() -> None:
    from bora.adapters.agent_container import ContainerCLIExecutor
    from bora.provider.targets import ActorPhysicalBinding, ExecutionTarget

    target = ExecutionTarget(
        target_id="tgt",
        group_id="g",
        generation=2,
        container_id="cid",
        state="ready",
    )
    actor = ActorPhysicalBinding(
        actor_id="a",
        group_id="g",
        target_id="tgt",
        uid=12000,
        gid=12000,
        home_container="/actor-homes/a",
        generation=1,
    )
    ex = ContainerCLIExecutor(
        kind="codex", model="m", container_id="cid", actor=actor, target=target, env={}
    )
    r = ex.invoke("hi")
    assert r.ok is False
    assert r.error == "generation_mismatch"


def test_target_dead_via_executor() -> None:
    from bora.adapters.agent_container import ContainerCLIExecutor
    from bora.provider.targets import ActorPhysicalBinding, ExecutionTarget

    target = ExecutionTarget(
        target_id="tgt", group_id="g", generation=1, container_id=None, state="dead"
    )
    actor = ActorPhysicalBinding(
        actor_id="a",
        group_id="g",
        target_id="tgt",
        uid=12000,
        gid=12000,
        home_container="/h",
        generation=1,
    )
    ex = ContainerCLIExecutor(
        kind="codex", model="m", container_id="", actor=actor, target=target, env={}
    )
    r = ex.invoke("hi")
    assert r.ok is False
    assert r.error == "target_dead"


def test_make_target_executor_generation_guard() -> None:
    """Parent path: make_target_executor raising generation_mismatch fail-closed."""

    def validate(a: str, p: str) -> dict:
        return {"ok": True, "target_id": "tgt", "generation": 1}

    def make(binding: SessionBinding) -> object:
        raise RuntimeError("generation_mismatch")

    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "x", "model": "m"}],
        agent_invocation_limit=1,
        attempt_id="attempt_ef004",
        extension_registry=registry_with_executor("x", object()),
        require_actor_id=True,
        validate_actor_profile=validate,
        make_target_executor=make,
        l1_container_only=True,
    )
    opened = svc.open_session(profile_id="p1", actor_id="a1")
    inv = svc.invoke(session_id=opened["session_id"], prompt="x")
    assert inv["ok"] is False
    # Exception type name or message both fail closed without host effect.
    err = str(inv.get("error") or "")
    assert err in {"generation_mismatch", "RuntimeError"} or "generation" in err
