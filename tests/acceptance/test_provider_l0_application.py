"""Provider L0 application checkpoint acceptance tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bora.adapters.package_fs import LocalPackageReader
from bora.application.run_provider_probe import run_provider_probe
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.load_and_lock import ConfigCore
from bora.provider.contract import ExecutableGrant, ProcessLaunchPlan
from bora.provider.errors import ProviderError
from bora.provider.outcomes import ProcessTerminalKind
from bora.provider.workspace_plan import WorkspacePlan
from bora.runtime.identity import IdentityFactory
from bora.runtime.outcomes import RuntimeTerminalKind

REPO = Path(__file__).resolve().parents[2]
MINIMAL = REPO / "examples" / "core" / "config-minimal"
HELPER = REPO / "tests" / "helpers" / "provider_probe_child.py"


def _lock():
    core = ConfigCore(package_reader=LocalPackageReader())
    return core.load_and_lock(
        MINIMAL, "config-minimal", capabilities=DeclarationCapabilityCatalog()
    )


def _attempt_for_lock(lock):
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, lock.digest)
    return f.new_attempt(trial)


@pytest.mark.asyncio
async def test_success_process(tmp_path: Path) -> None:
    lock = _lock()
    attempt = _attempt_for_lock(lock)
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=Path(sys.executable)),
        argv=(sys.executable, str(HELPER), "--mode", "exit0"),
        env={"PATH": "/usr/bin:/bin"},
        timeout_seconds=10.0,
    )
    record, outcome = await run_provider_probe(lock, plan)
    assert record.terminal == RuntimeTerminalKind.SUCCEEDED
    assert outcome.assurance == "l0"
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert outcome.exit_code == 0
    assert "PASS" not in str(outcome)


@pytest.mark.asyncio
async def test_outside_workdir(tmp_path: Path) -> None:
    lock = _lock()
    attempt = _attempt_for_lock(lock)
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="../x"),
        executable=ExecutableGrant(path=Path(sys.executable)),
        argv=(sys.executable, "-c", "print(1)"),
    )
    with pytest.raises(ProviderError) as ei:
        await run_provider_probe(lock, plan)
    assert ei.value.error_code == "outside_workdir"


@pytest.mark.asyncio
async def test_undeclared_executable(tmp_path: Path) -> None:
    lock = _lock()
    attempt = _attempt_for_lock(lock)
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=tmp_path / "no-such-bin"),
        argv=("no-such-bin",),
    )
    with pytest.raises(ProviderError) as ei:
        await run_provider_probe(lock, plan)
    assert ei.value.error_code == "undeclared_executable"


@pytest.mark.asyncio
async def test_timeout_tree(tmp_path: Path) -> None:
    lock = _lock()
    attempt = _attempt_for_lock(lock)
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=Path(sys.executable)),
        argv=(
            sys.executable,
            str(HELPER),
            "--mode",
            "ignore-term",
            "--path",
            "s.txt",
            "--seconds",
            "10",
        ),
        env={"PATH": "/usr/bin:/bin"},
        timeout_seconds=0.3,
    )
    record, outcome = await run_provider_probe(lock, plan)
    assert record.terminal == RuntimeTerminalKind.TIMED_OUT
    assert outcome.terminal == ProcessTerminalKind.TIMED_OUT
    assert "SIGKILL" in outcome.termination_actions
    assert outcome.writer_stop_confirmed


@pytest.mark.asyncio
async def test_cancel_tree(tmp_path: Path) -> None:
    from bora.runtime.cancellation import CancellationSignal

    lock = _lock()
    attempt = _attempt_for_lock(lock)
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=Path(sys.executable)),
        argv=(
            sys.executable,
            str(HELPER),
            "--mode",
            "write-loop",
            "--path",
            "w.txt",
            "--seconds",
            "10",
        ),
        env={"PATH": "/usr/bin:/bin"},
        timeout_seconds=30.0,
    )
    cancel = CancellationSignal()
    cancel.cancel()
    record, outcome = await run_provider_probe(lock, plan, cancellation=cancel)
    assert record.terminal == RuntimeTerminalKind.CANCELLED
    assert outcome.terminal == ProcessTerminalKind.CANCELLED


@pytest.mark.asyncio
async def test_idempotent_cleanup(tmp_path: Path) -> None:
    lock = _lock()
    attempt = _attempt_for_lock(lock)
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=Path(sys.executable)),
        argv=(sys.executable, str(HELPER), "--mode", "exit0"),
        env={"PATH": "/usr/bin:/bin"},
    )
    record, outcome = await run_provider_probe(lock, plan)
    assert outcome.cleanup_ok
    assert record.cleanup_calls == 1
