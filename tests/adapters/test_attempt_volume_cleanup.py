"""Attempt-owned Docker volumes and env containers die with the Attempt."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bora.adapters.environment_postgres import PostgresEnvironment
from bora.adapters.provider_docker.multi_actor import DockerMultiActorMixin
from bora.adapters.provider_docker.provider import DockerProvider
from bora.adapters.provider_docker.types import DockerImageLock, DockerRuntime
from bora.application.attempt.run_command_environment import (
    ENV_CONTAINER_MARKER,
    teardown_attempt_environment,
)
from bora.environment.manager import EnvironmentManager
from bora.provider.targets import (
    ExecutionTarget,
    IsolationMode,
    LogicalActor,
    LogicalGroup,
    LogicalIsolationTopology,
    TargetLedger,
)
from bora.runtime.identity import IdentityFactory


def _attempt():
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "c" * 64)
    return factory.new_attempt(trial)


def _topology() -> LogicalIsolationTopology:
    return LogicalIsolationTopology(
        mode=IsolationMode.SHARED_CONTAINER,
        groups=(LogicalGroup(group_id="g", actor_ids=("solver",)),),
        actors=(LogicalActor(actor_id="solver", group_id="g", profiles=("solver",)),),
    )


def _target(*, cid: str = "cid1", volume: str = "bora-home-abc") -> ExecutionTarget:
    return ExecutionTarget(
        target_id="t1",
        group_id="g",
        generation=1,
        container_id=cid,
        container_name="bora-agt-x",
        workspace_volume=volume,
        state="ready",
        image_digest="sha256:img",
        image_tag="bora-pkg:deadbeefcaf0",
    )


class _Proc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_postgres_stop_removes_anonymous_volumes() -> None:
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Proc:
        cmds.append(list(cmd))
        return _Proc()

    env = PostgresEnvironment(container_name="bora-env-deadbeef")
    with patch("bora.adapters.environment_postgres.subprocess.run", side_effect=fake_run):
        env.stop()
    assert ["docker", "rm", "-fv", "bora-env-deadbeef"] in cmds
    assert env.ready is False


def test_stop_agent_targets_drops_named_home_volume() -> None:
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Proc:
        cmds.append(list(cmd))
        return _Proc(returncode=0 if cmd[1] != "inspect" else 1)

    attempt = _attempt()
    runtime = DockerRuntime(
        attempt=attempt,
        image_lock=DockerImageLock(
            kind="t",
            platform="linux/arm64",
            image_tag="bora-pkg:x",
            image_digest="sha256:img",
            build_input_digest="sha256:d",
        ),
        target_ledger=TargetLedger(topology=_topology()),
    )
    target = _target()
    runtime.target_ledger.targets[target.target_id] = target  # type: ignore[union-attr]
    runtime.agent_container_ids = ["cid1"]

    with patch("bora.adapters.provider_docker.multi_actor.subprocess.run", side_effect=fake_run):
        DockerProvider().stop_agent_targets(runtime)

    assert ["docker", "rm", "-fv", "cid1"] in cmds
    assert ["docker", "volume", "rm", "-f", "bora-home-abc"] in cmds
    assert target.workspace_volume is None
    assert runtime.agent_container_ids == []


def test_prepare_rollback_removes_container_and_volume() -> None:
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Proc:
        cmds.append(list(cmd))
        return _Proc()

    attempt = _attempt()
    runtime = DockerRuntime(
        attempt=attempt,
        image_lock=DockerImageLock(
            kind="t",
            platform="linux/arm64",
            image_tag="bora-pkg:x",
            image_digest="sha256:img",
            build_input_digest="sha256:d",
        ),
        workdir_host=Path("/tmp/l1-work"),
    )
    started = _target()
    provider = DockerProvider()

    def fail_bootstrap(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("bootstrap-boom")

    with (
        patch.object(provider, "_start_long_lived_target", return_value=started),
        patch.object(provider, "_bootstrap_actor_fs", side_effect=fail_bootstrap),
        patch(
            "bora.adapters.provider_docker.multi_actor.subprocess.run",
            side_effect=fake_run,
        ),
    ):
        try:
            provider.prepare_agent_targets(runtime, _topology(), cred_root=Path("/tmp/creds"))
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected bootstrap failure")

    assert ["docker", "rm", "-fv", "cid1"] in cmds
    assert ["docker", "volume", "rm", "-f", "bora-home-abc"] in cmds
    assert started.workspace_volume is None


def test_teardown_closes_manager_and_marker_even_if_keep_workspace(
    tmp_path: Path,
) -> None:
    stopped: list[str] = []
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / ENV_CONTAINER_MARKER).write_text("bora-env-abc123\n", encoding="utf-8")

    class FakeEnv:
        def stop(self) -> None:
            stopped.append("manager")

    mgr = EnvironmentManager(attempt_id="a")
    mgr._resources["postgresql:bora-env-live"] = FakeEnv()
    ctx = SimpleNamespace(
        env_manager=mgr,
        agent_meta={"environment": {"resource_id": "postgresql:bora-env-live"}},
        package_root=pkg,
        run_dir=run_dir,
        attempt=None,
        lock=SimpleNamespace(),
        keep_workspace=True,
    )

    def fake_stop(self: PostgresEnvironment) -> None:
        stopped.append(self.container_name)

    with (
        patch(
            "bora.application.attempt.extension_hooks.hook_env_teardown",
            return_value=None,
        ),
        patch.object(PostgresEnvironment, "stop", fake_stop),
    ):
        teardown_attempt_environment(ctx)

    assert ctx.env_manager is None
    assert mgr.closed is True
    assert "manager" in stopped
    assert "bora-env-abc123" in stopped
    assert not (run_dir / ENV_CONTAINER_MARKER).exists()


def test_rm_target_never_prunes_unrelated_volumes() -> None:
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Proc:
        cmds.append(list(cmd))
        return _Proc()

    target = _target(volume="bora-home-only")
    with patch("bora.adapters.provider_docker.multi_actor.subprocess.run", side_effect=fake_run):
        DockerMultiActorMixin._rm_target(target)

    volume_rms = [c for c in cmds if c[:3] == ["docker", "volume", "rm"]]
    assert volume_rms == [["docker", "volume", "rm", "-f", "bora-home-only"]]
    assert not any("prune" in c for c in cmds)
    assert not any("bora-attempt:l1" in c for c in cmds)
    assert not any("registry" in " ".join(c) for c in cmds)
