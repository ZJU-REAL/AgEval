"""Executor child env projection never serializes secret values into evidence."""

from __future__ import annotations

from pathlib import Path

from bora.adapters import agent_pi
from bora.adapters.agent_pi import PiExecutor
from bora.evidence.store import AttemptEvidenceStore
from bora.runtime.agent_service import ParentAgentService


def test_pi_child_env_only_allowlisted_keys(monkeypatch: object) -> None:
    monkeypatch.setenv("ZAI_API_KEY", "SENTINEL_PI_KEY_NOT_FOR_DISK")  # type: ignore[attr-defined]
    monkeypatch.setenv("UNRELATED_SECRET", "should_not_project")  # type: ignore[attr-defined]
    env = agent_pi._child_env()
    assert "ZAI_API_KEY" in env
    assert "UNRELATED_SECRET" not in env
    # Values never asserted in logs — only key presence.


def test_shared_project_cli_child_env_allowlist(monkeypatch: object) -> None:
    from bora.adapters.child_env import project_cli_child_env

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "SENTINEL_CLAUDE")  # type: ignore[attr-defined]
    monkeypatch.setenv("UNRELATED_SECRET", "nope")  # type: ignore[attr-defined]
    env = project_cli_child_env("claude-code")
    assert env.get("ANTHROPIC_AUTH_TOKEN") == "SENTINEL_CLAUDE"
    assert "UNRELATED_SECRET" not in env


def test_agent_service_with_pi_offline_no_secret_in_evidence(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.setenv("BORA_OFFLINE_AGENT", "1")  # type: ignore[attr-defined]
    monkeypatch.setenv("ZAI_API_KEY", "SENTINEL_PI_KEY_NOT_FOR_DISK")  # type: ignore[attr-defined]
    store = AttemptEvidenceStore(
        root=tmp_path / "ev",
        attempt_id="a",
        sentinels=["SENTINEL_PI_KEY_NOT_FOR_DISK"],
    )
    svc = ParentAgentService(
        profiles=[{"id": "p1", "executor": "pi", "model": "claude-haiku-4-5"}],
        agent_invocation_limit=1,
        resolve_executor=lambda kind, model: PiExecutor(model=model),  # noqa: ARG005
        attempt_id="a",
        evidence_store=store,
    )
    sid = svc.open_session(profile_id="p1")["session_id"]
    svc.invoke(session_id=sid, prompt="hi")
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in store.root.rglob("*") if p.is_file()
    )
    assert "SENTINEL_PI_KEY_NOT_FOR_DISK" not in blob
