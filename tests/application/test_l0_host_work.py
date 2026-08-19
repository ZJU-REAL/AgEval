"""L0 host layout: cred/HOME/workspace stay outside the evidence run_dir."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ageval.application.attempt.attempt_stages import AttemptStageContext
from ageval.application.attempt.run_l0 import cleanup_l0, drop_l0_host_work, prepare_l0_attempt
from ageval.runtime.identity import IdentityFactory


def _attempt():
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "c" * 64)
    return factory.new_attempt(trial)


class _FakeCred:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cleanup_calls = 0

    def cleanup(self) -> None:
        self.cleanup_calls += 1
        if self.root.exists():
            self.root.joinpath("gone").write_text("1", encoding="utf-8")


class _FakeServer:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


def _lock() -> SimpleNamespace:
    return SimpleNamespace(
        digest="sha256:" + "a" * 64,
        agent_profiles=[{"id": "solver", "executor": "acp"}],
        parameters={},
        limits={"wall_time_seconds": 30, "agent_invocations": 1},
        provenance=None,
        job_overlay=None,
    )


def test_drop_l0_host_work_removes_dir(tmp_path: Path) -> None:
    host = tmp_path / "ageval-l0-x"
    (host / "workspace").mkdir(parents=True)
    (host / "attempt-home" / ".config").mkdir(parents=True)
    (host / "workspace" / "out.py").write_text("x = 1\n", encoding="utf-8")
    drop_l0_host_work(host, keep_workspace=False)
    assert not host.exists()


def test_drop_l0_host_work_keep_retains(tmp_path: Path) -> None:
    host = tmp_path / "ageval-l0-y"
    (host / "workspace").mkdir(parents=True)
    (host / "workspace" / "out.py").write_text("x = 1\n", encoding="utf-8")
    drop_l0_host_work(host, keep_workspace=True)
    assert (host / "workspace" / "out.py").is_file()


def test_cleanup_l0_drops_cred_and_host_not_run_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "result.json").write_text("{}\n", encoding="utf-8")
    host = tmp_path / "host"
    cred_root = host / "ageval-cred-x"
    cred_root.mkdir(parents=True)
    (cred_root / "openai_api_key").write_text("SECRET\n", encoding="utf-8")
    (host / "workspace").mkdir()
    cred = _FakeCred(cred_root)
    ctx = AttemptStageContext(
        package_root=tmp_path,
        lock=_lock(),
        run_dir=run_dir,
        attempt=_attempt(),
        cred=cred,
        host_work_root=host,
        workspace_host=host / "workspace",
    )
    cleanup_l0(ctx)
    assert cred.cleanup_calls == 1
    assert not host.exists()
    assert (run_dir / "result.json").is_file()
    assert not (run_dir / "ageval-cred-x").exists()
    assert not (run_dir / "attempt-home").exists()
    assert not (run_dir / "workspace").exists()


def test_prepare_l0_uses_host_root_not_run_dir(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _hook(_lock, value, *, ctx=None):  # type: ignore[no-untyped-def]
        captured["work_root"] = str(value["work_root"])
        captured["workspace_root"] = str(value["workspace_root"])
        root = Path(value["work_root"])
        cred_root = root / "ageval-cred-test"
        cred_root.mkdir()
        (cred_root / "openai_api_key").write_text("SECRET\n", encoding="utf-8")
        home = root / "attempt-home"
        home.mkdir()
        if ctx is not None:
            ctx.cred = _FakeCred(cred_root)
        return {"home_root": home}

    def _assemble(**kwargs):  # type: ignore[no-untyped-def]
        captured["workdir"] = str(kwargs.get("workdir") or "")
        captured["home"] = str(kwargs.get("home") or "")
        return SimpleNamespace(invocations_completed=0), 30.0, None

    monkeypatch.setattr(
        "ageval.application.attempt.extension_hooks.hook_home_overlay",
        _hook,
    )
    monkeypatch.setattr(
        "ageval.application.attempt.agent_service_assemble.assemble_parent_agent_service",
        _assemble,
    )
    monkeypatch.setattr(
        "ageval.runtime.agent_service_protocol.AgentServiceServer",
        lambda *_a, **_k: _FakeServer(),
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ctx = AttemptStageContext(
        package_root=tmp_path,
        lock=_lock(),
        run_dir=run_dir,
        attempt=_attempt(),
        dataset_root=tmp_path,
    )
    early = prepare_l0_attempt(ctx)
    assert early is None
    assert ctx.host_work_root is not None
    assert ctx.workspace_host == ctx.host_work_root / "workspace"
    assert ctx.run_dir not in ctx.host_work_root.parents
    assert ctx.host_work_root != ctx.run_dir
    assert captured["work_root"] == str(ctx.host_work_root)
    assert captured["workspace_root"] == str(ctx.workspace_host)
    assert captured["workdir"] == str(ctx.workspace_host)
    assert captured["home"] == str(ctx.host_work_root / "attempt-home")
    assert not list(run_dir.glob("ageval-cred-*"))
    assert not (run_dir / "attempt-home").exists()
    assert not (run_dir / "workspace").exists()
    assert ctx.agent_meta.get("workspace") == str(ctx.workspace_host)

    cleanup_l0(ctx)
    assert ctx.host_work_root is None or not ctx.host_work_root.exists()
