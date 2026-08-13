"""ParentAgentService actor_id + allowlist + no host fallback (Spec 18)."""

from __future__ import annotations

from tests.helpers.extension_registry import registry_with_executor

from bora.adapters.agent_contract import AgentResult
from bora.plugins.protocol import TargetPlacement
from bora.runtime.parent_agent_service import ParentAgentService


class _FakeExecutor:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def bind_to_target(self, placement: TargetPlacement) -> _FakeExecutor:
        del placement
        return self

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        self.prompts.append(prompt)
        return AgentResult(
            model="fake",
            text='{"answer": 42}',
            structured={"answer": 42},
            ok=True,
        )


def test_l1_requires_actor_id() -> None:
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "m"}],
        agent_invocation_limit=2,
        attempt_id="attempt_actortest001",
        offline_env="",
        extension_registry=registry_with_executor("fake", object()),
        require_actor_id=True,
        l1_container_only=True,
    )
    denied = svc.open_session(profile_id="p1")
    assert denied["ok"] is False
    assert denied["error"] == "actor_id_required"


def test_unknown_actor_fail_closed() -> None:
    def validate(actor_id: str, profile_id: str) -> dict:
        return {"ok": False, "error": "unknown_actor"}

    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "m"}],
        agent_invocation_limit=2,
        attempt_id="attempt_actortest002",
        offline_env="",
        extension_registry=registry_with_executor("fake", object()),
        require_actor_id=True,
        validate_actor_profile=validate,
        l1_container_only=True,
    )
    denied = svc.open_session(profile_id="p1", actor_id="nope")
    assert denied["ok"] is False
    assert denied["error"] == "unknown_actor"


def test_profile_not_allowed_for_actor() -> None:
    def validate(actor_id: str, profile_id: str) -> dict:
        return {"ok": False, "error": "profile_not_allowed"}

    svc = ParentAgentService(
        profiles=[
            {"id": "p1", "executor": "fake", "model": "m"},
            {"id": "p2", "executor": "fake", "model": "m"},
        ],
        agent_invocation_limit=2,
        attempt_id="attempt_actortest003",
        offline_env="",
        extension_registry=registry_with_executor("fake", object()),
        require_actor_id=True,
        validate_actor_profile=validate,
        l1_container_only=True,
    )
    denied = svc.open_session(profile_id="p2", actor_id="a1")
    assert denied["ok"] is False
    assert denied["error"] == "profile_not_allowed"


def test_target_executor_path_no_host() -> None:
    fake = _FakeExecutor()

    def validate(actor_id: str, profile_id: str) -> dict:
        return {"ok": True, "target_id": "tgt_x", "generation": 1}

    def resolve_placement(binding):
        assert binding.actor_id == "a1"
        assert binding.target_id == "tgt_x"
        return TargetPlacement(container_id="cid", uid=1, gid=1)

    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "m"}],
        agent_invocation_limit=2,
        attempt_id="attempt_actortest004",
        offline_env="",
        extension_registry=registry_with_executor("fake", fake),
        require_actor_id=True,
        validate_actor_profile=validate,
        resolve_placement=resolve_placement,
        l1_container_only=True,
    )
    opened = svc.open_session(profile_id="p1", actor_id="a1")
    assert opened["ok"] is True
    assert opened["target_id"] == "tgt_x"
    r = svc.invoke(session_id=opened["session_id"], prompt="hi")
    assert r["ok"] is True
    assert len(fake.prompts) == 1


def test_parent_service_has_no_host_fallback_count() -> None:
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "m"}],
        agent_invocation_limit=1,
        attempt_id="attempt_actortest005",
        offline_env="",
        extension_registry=registry_with_executor("fake", object()),
        l1_container_only=True,
    )
    assert not hasattr(svc, "host_fallback_count")


def test_l1_unbound_invoke_is_error_not_counter() -> None:
    def validate(actor_id: str, profile_id: str) -> dict:
        return {"ok": True, "target_id": "tgt", "generation": 1}

    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "m"}],
        agent_invocation_limit=1,
        attempt_id="attempt_actortest006",
        offline_env="",
        extension_registry=registry_with_executor("fake", object()),
        require_actor_id=True,
        validate_actor_profile=validate,
        resolve_placement=None,
        l1_container_only=True,
    )
    opened = svc.open_session(profile_id="p1", actor_id="a1")
    assert opened["ok"] is True
    inv = svc.invoke(session_id=opened["session_id"], prompt="x")
    assert inv["ok"] is False
    assert inv["error"] == "l1_executor_unbound"
