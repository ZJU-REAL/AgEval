"""Issue #5: agent_profiles gate (no use_agent_session flag)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ageval.application.attempt.attempt_stages import AttemptStageContext, DockerL1Stages
from ageval.application.attempt.run_l1_phases import prepare_l1_session
from ageval.runtime.identity import IdentityFactory


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
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "d" * 64)
    attempt = factory.new_attempt(trial)
    ctx = AttemptStageContext(
        package_root=tmp_path,
        lock=lock,
        run_dir=tmp_path / "run",
        attempt=attempt,
        task_id="no-agent",
    )
    ctx.run_dir.mkdir()
    ok = prepare_l1_session(ctx)
    assert ok is False
    assert ctx.exit_code == 2
    err = ctx.result_doc.get("error") or {}
    assert err.get("kind") == "l1_dispatch_unsupported" or ctx.result_doc.get("status") == "ERROR"
    stages = DockerL1Stages(ctx=ctx)
    assert stages.ctx is ctx
