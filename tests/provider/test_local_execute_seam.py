"""LocalProcessProvider execute / execute_sync seam tests."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from ageval.adapters.provider_local import LocalProcessProvider
from ageval.provider.contract import ExecutableGrant, ProcessLaunchPlan, TerminationPolicy
from ageval.provider.outcomes import ProcessTerminalKind
from ageval.provider.workspace_plan import WorkspacePlan
from ageval.runtime.identity import IdentityFactory

HELPER = Path(__file__).resolve().parents[1] / "helpers" / "provider_probe_child.py"


def _attempt():
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, "sha256:" + "b" * 64)
    return f.new_attempt(trial)


def _plan(
    tmp_path: Path,
    *argv: str,
    timeout: float | None = 10.0,
    pass_fds: tuple[int, ...] = (),
    stdin_bytes: bytes | None = None,
    env: dict[str, str] | None = None,
) -> ProcessLaunchPlan:
    attempt = _attempt()
    return ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=Path(sys.executable)),
        argv=(sys.executable, str(HELPER), *argv),
        env=env or {"PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout_seconds=timeout,
        pass_fds=pass_fds,
        stdin_bytes=stdin_bytes,
    )


@pytest.mark.asyncio
async def test_execute_success(tmp_path: Path) -> None:
    provider = LocalProcessProvider()
    plan = _plan(tmp_path, "--mode", "exit0")
    outcome = await provider.execute(plan)
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert outcome.exit_code == 0
    assert "hello-stdout" in outcome.stdout_summary
    assert outcome.writer_stop_confirmed
    assert outcome.cleanup_ok


@pytest.mark.asyncio
async def test_execute_spawn_failed_returns_outcome(tmp_path: Path) -> None:
    attempt = _attempt()
    # Regular file without +x → OSError at spawn (after prepare succeeds).
    bad = tmp_path / "not-executable"
    bad.write_bytes(b"\x00not-an-exe")
    bad.chmod(0o644)
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=bad),
        argv=(str(bad),),
        env={"PATH": "/usr/bin:/bin"},
        timeout_seconds=5.0,
    )
    provider = LocalProcessProvider()
    outcome = await provider.execute(plan)
    assert outcome.terminal == ProcessTerminalKind.SPAWN_FAILED
    assert outcome.exit_code is None


@pytest.mark.asyncio
async def test_execute_pass_fds(tmp_path: Path) -> None:
    read_fd, write_fd = os.pipe()
    try:
        attempt = _attempt()
        code = f"import os, sys\nos.write({write_fd}, b'passfd-ok')\nsys.exit(0)\n"
        plan = ProcessLaunchPlan(
            attempt=attempt,
            workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
            executable=ExecutableGrant(path=Path(sys.executable)),
            argv=(sys.executable, "-c", code),
            env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
            timeout_seconds=10.0,
            pass_fds=(write_fd,),
        )
        provider = LocalProcessProvider()
        outcome = await provider.execute(plan)
        assert outcome.terminal == ProcessTerminalKind.EXITED
        assert outcome.exit_code == 0
        # Close write end in parent so read can see EOF after child writes.
        os.close(write_fd)
        write_fd = -1
        got = os.read(read_fd, 64)
        assert got == b"passfd-ok"
    finally:
        if write_fd >= 0:
            os.close(write_fd)
        os.close(read_fd)


@pytest.mark.asyncio
async def test_execute_stdin_bytes(tmp_path: Path) -> None:
    attempt = _attempt()
    code = "import sys; sys.stdout.write(sys.stdin.read()); sys.stdout.flush()"
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=Path(sys.executable)),
        argv=(sys.executable, "-c", code),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout_seconds=10.0,
        stdin_bytes=b"stdin-echo-ok",
    )
    provider = LocalProcessProvider()
    outcome = await provider.execute(plan)
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert outcome.exit_code == 0
    assert "stdin-echo-ok" in outcome.stdout_summary


@pytest.mark.asyncio
async def test_policy_skipped_when_writer_gone(tmp_path: Path) -> None:
    calls: list[str] = []

    def terminate() -> str | None:
        calls.append("terminate")
        return "policy_cleanup"

    provider = LocalProcessProvider()
    plan = _plan(tmp_path, "--mode", "exit0")
    outcome = await provider.execute(
        plan,
        termination=TerminationPolicy(terminate=terminate, is_alive=lambda: False),
    )
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert calls == []
    assert "policy_cleanup" not in outcome.termination_actions
    assert outcome.writer_stop_confirmed


@pytest.mark.asyncio
async def test_policy_fires_without_self_confirm(tmp_path: Path) -> None:
    calls: list[str] = []

    def terminate() -> str | None:
        calls.append("terminate")
        return "policy_cleanup"

    provider = LocalProcessProvider()
    plan = _plan(tmp_path, "--mode", "exit0")
    outcome = await provider.execute(
        plan,
        termination=TerminationPolicy(terminate=terminate, is_alive=lambda: True),
    )
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert calls == ["terminate"]
    assert "policy_cleanup" in outcome.termination_actions
    assert outcome.writer_stop_confirmed is False
    assert outcome.cleanup_warning is not None


@pytest.mark.asyncio
async def test_policy_probe_exception_is_not_death(tmp_path: Path) -> None:
    def is_alive() -> bool:
        raise RuntimeError("probe failed")

    provider = LocalProcessProvider()
    plan = _plan(tmp_path, "--mode", "exit0")
    outcome = await provider.execute(
        plan,
        termination=TerminationPolicy(terminate=lambda: "policy_cleanup", is_alive=is_alive),
    )
    assert outcome.writer_stop_confirmed is False


def test_execute_sync_without_running_loop(tmp_path: Path) -> None:
    provider = LocalProcessProvider()
    plan = _plan(tmp_path, "--mode", "exit0")
    outcome = provider.execute_sync(plan)
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert outcome.exit_code == 0


@pytest.mark.asyncio
async def test_execute_sync_inside_running_loop(tmp_path: Path) -> None:
    provider = LocalProcessProvider()
    plan = _plan(tmp_path, "--mode", "exit0")
    outcome = await asyncio.to_thread(provider.execute_sync, plan)
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert outcome.exit_code == 0
