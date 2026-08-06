"""Generation fencing for session → target binding."""

from __future__ import annotations

from bora.adapters.agent_contract import AgentResult
from bora.runtime.agent_service import ParentAgentService, SessionBinding


def test_open_binds_generation() -> None:
    def validate(actor_id: str, profile_id: str) -> dict:
        return {"ok": True, "target_id": "tgt_1", "generation": 3}

    def make_exec(binding: SessionBinding):
        assert binding.generation == 3

        class _E:
            def invoke(self, prompt: str, **kw: object) -> AgentResult:
                return AgentResult(model="m", text="{}", structured={"answer": 1}, ok=True)

        return _E()

    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "x", "model": "m"}],
        agent_invocation_limit=1,
        resolve_executor=lambda *a, **k: (_ for _ in ()).throw(AssertionError()),
        attempt_id="attempt_gen001",
        require_actor_id=True,
        validate_actor_profile=validate,
        make_target_executor=make_exec,
        l1_container_only=True,
    )
    opened = svc.open_session(profile_id="p1", actor_id="a1")
    assert opened["generation"] == 3
    r = svc.invoke(session_id=opened["session_id"], prompt="x")
    assert r["ok"] is True
