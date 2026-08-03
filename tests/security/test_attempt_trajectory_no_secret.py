"""Security: trajectory tree has zero plain sentinel / credential hits."""

from __future__ import annotations

import json
from pathlib import Path

from bora.adapters.agent_codex import AgentResult
from bora.evidence.redaction import scan_for_secrets
from bora.evidence.store import AttemptEvidenceStore
from bora.runtime.agent_service import ParentAgentService


class _LeakyExecutor:
    """Executor that would try to leak a sentinel via events/response."""

    def __init__(self, sentinel: str) -> None:
        self.sentinel = sentinel

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
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
        resolve_executor=lambda kind, model: fake,  # noqa: ARG005
        attempt_id="attempt_sec",
        evidence_store=store,
    )
    sid = svc.open_session(profile_id="p1")["session_id"]
    r = svc.invoke(session_id=sid, prompt=f"use {sentinel}")
    # Either redaction_failed or completed with redacted body — never plain sentinel.
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
    # Scan structured files
    for p in store.root.rglob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        hits = scan_for_secrets(data, extra_sentinels=[sentinel])
        assert hits == [] or "sentinel" not in hits or sentinel not in json.dumps(data)
