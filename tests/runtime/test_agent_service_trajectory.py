"""Agent Service writes per-invocation trajectory before return."""

from __future__ import annotations

import json
from pathlib import Path

from bora.adapters.agent_codex import AgentResult
from bora.evidence.store import AttemptEvidenceStore
from bora.runtime.agent_service import ParentAgentService


class _FakeExecutor:
    def __init__(self, *, fail_on: int | None = None, error: str = "exit_1") -> None:
        self.n = 0
        self.fail_on = fail_on
        self.error = error

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        self.n += 1
        if self.fail_on is not None and self.n == self.fail_on:
            return AgentResult(
                model="fake",
                text="",
                structured=None,
                ok=False,
                error=self.error,
                events=({"type": "lifecycle", "phase": "failed", "source": "fake"},),
                stderr="diag",
            )
        return AgentResult(
            model="fake",
            text=f'{{"answer": {40 + self.n}}}',
            structured={"answer": 40 + self.n},
            ok=True,
            events=(
                {"type": "lifecycle", "phase": "start", "source": "fake"},
                {"type": "message", "text": f"answer {40 + self.n}", "source": "fake"},
            ),
            usage={"input_tokens": 1, "output_tokens": 1},
        )


def test_each_invoke_has_directory(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "ev", attempt_id="attempt_t1")
    fake = _FakeExecutor()
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "fake"}],
        agent_invocation_limit=2,
        resolve_executor=lambda kind, model: fake,  # noqa: ARG005
        attempt_id="attempt_t1",
        evidence_store=store,
    )
    sid = svc.open_session(profile_id="p1")["session_id"]
    r1 = svc.invoke(session_id=sid, prompt="first")
    r2 = svc.invoke(session_id=sid, prompt="second")
    assert r1["ok"] and r2["ok"]
    assert r1["invocation_id"] and r2["invocation_id"]
    dirs = store.list_invocations()
    assert len(dirs) == 2
    for d in dirs:
        meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
        assert meta["status"] == "completed"
        assert (d / "request.json").is_file()
        assert (d / "final-response.json").is_file()
        events = (d / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(events) >= 1


def test_terminal_before_return(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "ev", attempt_id="attempt_t2")
    fake = _FakeExecutor()
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "fake"}],
        agent_invocation_limit=1,
        resolve_executor=lambda kind, model: fake,  # noqa: ARG005
        attempt_id="attempt_t2",
        evidence_store=store,
    )
    sid = svc.open_session(profile_id="p1")["session_id"]
    r = svc.invoke(session_id=sid, prompt="one")
    # After return, metadata must already be terminal.
    meta = json.loads(
        (store.list_invocations()[0] / "metadata.json").read_text(encoding="utf-8")
    )
    assert meta["status"] == "completed"
    assert r["evidence_relative"] is not None
