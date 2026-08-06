"""Issue #5: agent_profiles gate (no use_agent_session flag)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from bora.application.run_l1 import run_l1_attempt


def test_l1_empty_profiles_without_profiles_is_unsupported(tmp_path: Path) -> None:
    lock = SimpleNamespace(
        task_id="no-agent",
        parameters={},
        agent_profiles=[],
        digest="sha256:dead",
        provider={"kind": "docker"},
        limits={},
        evaluation={},
        harness={"entrypoint": "harness:run"},
    )
    code, doc, _ = run_l1_attempt(
        package_root=tmp_path,
        lock=lock,
        run_dir=tmp_path / "run",
        agent_meta={},
        allow_offline_agent=True,
    )
    assert code == 2
    err = doc.get("error") or {}
    assert err.get("kind") == "l1_dispatch_unsupported" or doc.get("status") == "ERROR"
