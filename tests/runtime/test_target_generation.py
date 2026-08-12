"""Generation fencing for session → target binding."""

from __future__ import annotations

from tests.helpers.extension_registry import registry_with_executor

from bora.adapters.agent_contract import AgentResult
from bora.plugins.protocol import TargetPlacement
from bora.runtime.parent_agent_service import ParentAgentService


class _E:
    def bind_to_target(self, placement: TargetPlacement) -> _E:
        del placement
        return self

    def invoke(self, prompt: str, **kw: object) -> AgentResult:
        del prompt, kw
        return AgentResult(model="m", text="{}", structured={"answer": 1}, ok=True)


def test_open_binds_generation() -> None:
    def validate(actor_id: str, profile_id: str) -> dict:
        return {"ok": True, "target_id": "tgt_1", "generation": 3}

    def resolve_placement(binding):
        assert binding.generation == 3
        return TargetPlacement(container_id="cid", uid=1, gid=1)

    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "x", "model": "m"}],
        agent_invocation_limit=1,
        attempt_id="attempt_gen001",
        offline_env="",
        extension_registry=registry_with_executor("x", _E()),
        require_actor_id=True,
        validate_actor_profile=validate,
        resolve_placement=resolve_placement,
        l1_container_only=True,
    )
    opened = svc.open_session(profile_id="p1", actor_id="a1")
    assert opened["generation"] == 3
    r = svc.invoke(session_id=opened["session_id"], prompt="x")
    assert r["ok"] is True
