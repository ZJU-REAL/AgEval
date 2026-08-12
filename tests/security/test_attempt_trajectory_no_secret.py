"""Security: trajectory tree has zero plain sentinel / credential hits."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.extension_registry import registry_with_executor

from bora.adapters.agent_contract import AgentResult
from bora.evidence.store import AttemptEvidenceStore
from bora.runtime.parent_agent_service import ParentAgentService


class _LeakyExecutor:
    """Executor that would try to leak a sentinel via events/response."""

    def __init__(self, sentinel: str) -> None:
        self.sentinel = sentinel

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        del prompt, kwargs
        return AgentResult(
            model="fake",
            text=f'{{"answer": 1, "note": "{self.sentinel}"}}',
            structured={"answer": 1, "note": self.sentinel},
            ok=True,
            events=(
                {
                    "type": "message",
                    "text": f"token={self.sentinel}",
                    "source": "fake",
                },
            ),
            stderr=f"auth cookie={self.sentinel}\n",
            source_refs=(),
        )


def test_sentinel_never_on_disk(tmp_path: Path) -> None:
    sentinel = "TRAJ_SEC_SENTINEL_7c9e2f"
    store = AttemptEvidenceStore(
        root=tmp_path / "ev",
        attempt_id="attempt_sec",
        sentinels=[sentinel],
    )
    fake = _LeakyExecutor(sentinel)
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "fake", "model": "fake"}],
        agent_invocation_limit=1,
        attempt_id="attempt_sec",
        offline_env="",
        extension_registry=registry_with_executor("fake", fake),
        evidence_store=store,
    )
    sid = svc.open_session(profile_id="p1")["session_id"]
    r = svc.invoke(session_id=sid, prompt=f"use {sentinel}")
    assert r.get("error") in (None, "redaction_failed") or r.get("ok") is False
    blob_parts: list[str] = []
    for p in store.root.rglob("*"):
        if p.is_file():
            try:
                blob_parts.append(p.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                continue
    tree = "\n".join(blob_parts)
    assert sentinel not in tree
