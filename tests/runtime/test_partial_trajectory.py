"""Partial trajectory for crash / timeout / cancel — no pseudo final response."""

from __future__ import annotations

import json
from pathlib import Path

from bora.adapters.agent_codex import AgentResult
from bora.evidence.store import AttemptEvidenceStore
from bora.runtime.agent_service import ParentAgentService


class _CrashExecutor:
    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        raise RuntimeError("simulated_executor_crash")


class _TimeoutExecutor:
    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        return AgentResult(
            model="fake",
            text="",
            structured=None,
            ok=False,
            error="TimeoutExpired",
            events=({"type": "lifecycle", "phase": "timeout", "source": "fake"},),
        )


class _CancelExecutor:
    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        return AgentResult(
            model="fake",
            text="",
            structured=None,
            ok=False,
            error="cancelled",
            events=({"type": "lifecycle", "phase": "cancelled", "source": "fake"},),
        )


class _OkThen:
    def __init__(self, second: object) -> None:
        self.n = 0
        self.second = second

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        self.n += 1
        if self.n == 1:
            return AgentResult(
                model="fake",
                text='{"answer": 40}',
                structured={"answer": 40},
                ok=True,
                events=({"type": "ok", "source": "fake"},),
            )
        return self.second.invoke(prompt, **kwargs)  # type: ignore[attr-defined]


def _run(tmp_path: Path, second: object, expected_status: str) -> Path:
    store = AttemptEvidenceStore(root=tmp_path / "ev", attempt_id="attempt_p")
    chain = _OkThen(second)
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "fake"}],
        agent_invocation_limit=2,
        resolve_executor=lambda kind, model: chain,  # noqa: ARG005
        attempt_id="attempt_p",
        evidence_store=store,
    )
    sid = svc.open_session(profile_id="p1")["session_id"]
    assert svc.invoke(session_id=sid, prompt="first")["ok"]
    r2 = svc.invoke(session_id=sid, prompt="second")
    assert r2["ok"] is False
    dirs = store.list_invocations()
    assert len(dirs) == 2
    meta2 = json.loads((dirs[1] / "metadata.json").read_text(encoding="utf-8"))
    assert meta2["status"] == expected_status
    assert not (dirs[1] / "final-response.json").exists()
    # First still completed with final response
    assert (dirs[0] / "final-response.json").is_file()
    return dirs[1]


def test_crash_partial(tmp_path: Path) -> None:
    _run(tmp_path, _CrashExecutor(), "crash")


def test_timeout_partial(tmp_path: Path) -> None:
    _run(tmp_path, _TimeoutExecutor(), "timeout")


def test_cancel_partial(tmp_path: Path) -> None:
    _run(tmp_path, _CancelExecutor(), "cancelled")
