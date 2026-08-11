"""Hard ceiling: N+1 agent invoke and env action denied before external effect."""

from __future__ import annotations

from pathlib import Path

from bora.adapters.agent_contract import AgentResult
from bora.environment.manager import EnvironmentManager
from bora.evidence.store import AttemptEvidenceStore, parse_jsonl_recover
from bora.runtime.parent_agent_service import ParentAgentService
from tests.helpers.extension_registry import registry_with_executor


class _CountingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        self.calls += 1
        return AgentResult(
            model="fake",
            text='{"ok":true}',
            structured={"ok": True},
            ok=True,
            events=({"type": "ok", "source": "fake"},),
        )


def test_agent_n_plus_one_no_external_call(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "e", attempt_id="a")
    fake = _CountingExecutor()
    svc = ParentAgentService(
        profiles=[{"id": "p", "executor": "fake", "model": "m"}],
        agent_invocation_limit=1,
        attempt_id="a",
        extension_registry=registry_with_executor("fake", fake),
        evidence_store=store,
    )
    sid = svc.open_session(profile_id="p")["session_id"]
    assert svc.invoke(session_id=sid, prompt="1")["ok"] is True
    denied = svc.invoke(session_id=sid, prompt="2")
    assert denied["ok"] is False
    assert denied["error"] == "agent_invocation_limit"
    assert fake.calls == 1  # N+1 never reached executor


def test_env_n_plus_one_deny_effect(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "e", attempt_id="a")
    mgr = EnvironmentManager(attempt_id="a", action_limit=1, evidence_store=store)
    mgr._resources["postgresql:x"] = type(
        "E",
        (),
        {"action": lambda self, a, args=None: {"ok": True, "executed": True}},
    )()
    assert mgr.action("postgresql:x", "execute", {"sql": "SELECT 1"})["ok"] is True
    denied = mgr.action("postgresql:x", "execute", {"sql": "SELECT 2"})
    assert denied["ok"] is False
    assert denied["error"] == "environment_action_limit_exceeded"
    effects = parse_jsonl_recover(store.root / "effects.jsonl")
    assert any(e.get("reason") == "environment_action_limit_exceeded" for e in effects)
