"""Executor child env projection never serializes secret values into evidence."""

from __future__ import annotations

from pathlib import Path

from bora.adapters.agent_acp import AcpExecutor
from bora.adapters.child_env import project_cli_child_env
from bora.evidence.store import AttemptEvidenceStore
from bora.runtime.agent_service import ParentAgentService


def test_shared_project_cli_child_env_allowlist(monkeypatch: object) -> None:
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "SENTINEL_CLAUDE")  # type: ignore[attr-defined]
    monkeypatch.setenv("UNRELATED_SECRET", "nope")  # type: ignore[attr-defined]
    env = project_cli_child_env("claude-code")
    assert env.get("ANTHROPIC_AUTH_TOKEN") == "SENTINEL_CLAUDE"
    assert "UNRELATED_SECRET" not in env


def test_agent_service_with_acp_offline_no_secret_in_evidence(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("BORA_OFFLINE_AGENT", "1")  # type: ignore[attr-defined]
    monkeypatch.setenv("ZHIPU_API_KEY", "SENTINEL_ACP_KEY_NOT_FOR_DISK")  # type: ignore[attr-defined]
    store = AttemptEvidenceStore(
        root=tmp_path / "ev",
        attempt_id="a",
        sentinels=["SENTINEL_ACP_KEY_NOT_FOR_DISK"],
    )
    svc = ParentAgentService(
        profiles=[
            {
                "id": "p1",
                "executor": "acp",
                "model": "entry-default",
                "options": {"entry": "opencode"},
            }
        ],
        agent_invocation_limit=1,
        resolve_executor=lambda kind, model, **kw: AcpExecutor(
            entry_id=str(kw.get("entry") or "opencode"), model=model
        ),
        attempt_id="a",
        evidence_store=store,
    )
    sid = svc.open_session(profile_id="p1")["session_id"]
    svc.invoke(session_id=sid, prompt="hi")
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in store.root.rglob("*") if p.is_file()
    )
    assert "SENTINEL_ACP_KEY_NOT_FOR_DISK" not in blob
