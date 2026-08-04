"""ParentAgentService actor_id + allowlist + no host fallback (Spec 18)."""

from __future__ import annotations

from bora.adapters.agent_codex import AgentResult
from bora.runtime.agent_service import ParentAgentService, SessionBinding


class _FakeExecutor:
    def __init__(self) -> None:
        self.prompts: list[str] = []

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
        resolve_executor=lambda *a, **k: (_ for _ in ()).throw(AssertionError("host")),
        attempt_id="attempt_actortest001",
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
        resolve_executor=lambda *a, **k: (_ for _ in ()).throw(AssertionError("host")),
        attempt_id="attempt_actortest002",
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
        resolve_executor=lambda *a, **k: (_ for _ in ()).throw(AssertionError("host")),
        attempt_id="attempt_actortest003",
        require_actor_id=True,
        validate_actor_profile=validate,
        l1_container_only=True,
    )
    denied = svc.open_session(profile_id="p2", actor_id="a1")
    assert denied["ok"] is False
    assert denied["error"] == "profile_not_allowed"


def test_target_executor_path_no_host() -> None:
    fake = _FakeExecutor()
    host_calls = {"n": 0}

    def host_resolve(*a, **k):
        host_calls["n"] += 1
        raise AssertionError("must not host resolve")

    def validate(actor_id: str, profile_id: str) -> dict:
        return {"ok": True, "target_id": "tgt_x", "generation": 1}

    def make_exec(binding: SessionBinding):
        assert binding.actor_id == "a1"
        assert binding.target_id == "tgt_x"
        return fake

    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "m"}],
        agent_invocation_limit=2,
        resolve_executor=host_resolve,
        attempt_id="attempt_actortest004",
        require_actor_id=True,
        validate_actor_profile=validate,
        make_target_executor=make_exec,
        l1_container_only=True,
    )
    opened = svc.open_session(profile_id="p1", actor_id="a1")
    assert opened["ok"] is True
    assert opened["target_id"] == "tgt_x"
    r = svc.invoke(session_id=opened["session_id"], prompt="hi")
    assert r["ok"] is True
    assert host_calls["n"] == 0
    assert len(fake.prompts) == 1
