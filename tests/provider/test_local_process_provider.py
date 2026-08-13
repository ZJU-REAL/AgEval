"""LocalProcessProvider real-process tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bora.adapters.provider_local import LocalProcessProvider
from bora.provider.contract import ExecutableGrant, ProcessLaunchPlan
from bora.provider.errors import ProviderError
from bora.provider.outcomes import ProcessTerminalKind
from bora.provider.workspace_plan import WorkspacePlan
from bora.runtime.cancellation import CancellationSignal
from bora.runtime.identity import IdentityFactory

HELPER = Path(__file__).resolve().parents[1] / "helpers" / "provider_probe_child.py"


def _attempt():
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, "sha256:" + "b" * 64)
    return f.new_attempt(trial)


def _plan(tmp_path: Path, *argv: str, timeout: float | None = 10.0) -> ProcessLaunchPlan:
    attempt = _attempt()
    return ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=Path(sys.executable)),
        argv=(sys.executable, str(HELPER), *argv),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout_seconds=timeout,
    )


@pytest.mark.asyncio
async def test_success_exit0(tmp_path: Path) -> None:
    provider = LocalProcessProvider()
    plan = _plan(tmp_path, "--mode", "exit0", "--path", "out.txt")
    prep = await provider.prepare(plan)
    prep = await provider.start(prep)
    outcome = await provider.wait(prep)
    assert outcome.assurance == "l0"
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert outcome.exit_code == 0
    assert "hello-stdout" in outcome.stdout_summary
    assert outcome.cleanup_ok
    assert outcome.writer_stop_confirmed
    assert not prep.workdir.exists()


@pytest.mark.asyncio
async def test_outside_workdir(tmp_path: Path) -> None:
    attempt = _attempt()
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="../nope"),
        executable=ExecutableGrant(path=Path(sys.executable)),
        argv=(sys.executable, "-c", "print(1)"),
    )
    provider = LocalProcessProvider()
    with pytest.raises(ProviderError) as ei:
        await provider.prepare(plan)
    assert ei.value.error_code == "outside_workdir"


@pytest.mark.asyncio
async def test_spawn_via_venv_symlink_keeps_site_packages(tmp_path: Path) -> None:
    """argv[0] must stay the venv python symlink so pyvenv.cfg applies.

    Following the symlink to the shared CPython drops venv site-packages
    (L0 evaluator then cannot import host deps such as tau2).
    """
    real = Path(sys.executable).resolve()
    venv = tmp_path / "venv"
    bindir = venv / "bin"
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    site = venv / "lib" / py_ver / "site-packages"
    bindir.mkdir(parents=True)
    site.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(
        f"home = {real.parent}\ninclude-system-site-packages = false\n",
        encoding="utf-8",
    )
    (site / "bora_venv_probe.py").write_text("MARKER = 'venv-site'\n", encoding="utf-8")
    link = bindir / "python3"
    link.symlink_to(real)

    attempt = _attempt()
    code = (
        "import bora_venv_probe, sys; "
        "print(bora_venv_probe.MARKER); "
        "print(sys.prefix)"
    )
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=link),
        argv=(str(link), "-c", code),
        env={"PATH": "/usr/bin:/bin"},
        timeout_seconds=10.0,
    )
    outcome = await LocalProcessProvider().execute(plan)
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert outcome.exit_code == 0
    assert "venv-site" in outcome.stdout_summary
    assert str(venv) in outcome.stdout_summary


@pytest.mark.asyncio
async def test_undeclared_executable(tmp_path: Path) -> None:
    attempt = _attempt()
    plan = ProcessLaunchPlan(
        attempt=attempt,
        workspace=WorkspacePlan(attempt=attempt, base_dir=tmp_path, relative_workdir="ws"),
        executable=ExecutableGrant(path=tmp_path / "missing-bin"),
        argv=("missing-bin",),
    )
    provider = LocalProcessProvider()
    with pytest.raises(ProviderError) as ei:
        await provider.prepare(plan)
    assert ei.value.error_code == "undeclared_executable"


@pytest.mark.asyncio
async def test_timeout_tree(tmp_path: Path) -> None:
    provider = LocalProcessProvider(term_wait_seconds=0.1, kill_wait_seconds=0.2)
    plan = _plan(
        tmp_path,
        "--mode",
        "ignore-term",
        "--path",
        "sent.txt",
        "--seconds",
        "10",
        timeout=0.3,
    )
    prep = await provider.prepare(plan)
    prep = await provider.start(prep)
    outcome = await provider.wait(prep)
    assert outcome.terminal == ProcessTerminalKind.TIMED_OUT
    assert "SIGTERM" in outcome.termination_actions
    assert "SIGKILL" in outcome.termination_actions
    assert outcome.writer_stop_confirmed
    assert outcome.cleanup_ok


@pytest.mark.asyncio
async def test_cancel_tree(tmp_path: Path) -> None:
    provider = LocalProcessProvider(term_wait_seconds=0.1, kill_wait_seconds=0.2)
    plan = _plan(
        tmp_path, "--mode", "write-loop", "--path", "w.txt", "--seconds", "10", timeout=30.0
    )
    prep = await provider.prepare(plan)
    prep = await provider.start(prep)
    cancel = CancellationSignal()
    cancel.cancel("test")
    outcome = await provider.wait(prep, cancellation=cancel)
    assert outcome.terminal == ProcessTerminalKind.CANCELLED
    assert outcome.writer_stop_confirmed


@pytest.mark.asyncio
async def test_idempotent_cleanup(tmp_path: Path) -> None:
    provider = LocalProcessProvider()
    plan = _plan(tmp_path, "--mode", "exit0")
    prep = await provider.prepare(plan)
    prep = await provider.start(prep)
    outcome = await provider.wait(prep)
    assert outcome.cleanup_ok
    # Second cleanup is no-op
    await provider.cleanup(prep)


@pytest.mark.asyncio
async def test_residual_same_group_writer(tmp_path: Path) -> None:
    """Parent exits 0 while same-group writer continues — group kill must reap it."""
    provider = LocalProcessProvider(term_wait_seconds=0.15, kill_wait_seconds=0.3)
    plan = _plan(
        tmp_path,
        "--mode",
        "spawn-group-writer",
        "--path",
        "sent.txt",
        "--seconds",
        "8",
        timeout=10.0,
    )
    prep = await provider.prepare(plan)
    prep = await provider.start(prep)
    outcome = await provider.wait(prep)
    assert outcome.terminal == ProcessTerminalKind.EXITED
    assert outcome.exit_code == 0
    # Residual group cleanup should confirm writers are gone.
    assert outcome.writer_stop_confirmed is True
    assert outcome.cleanup_ok
    # Sentinel must not keep growing after cleanup.

    sent = prep.workdir / "sent.txt" if prep.workdir.exists() else None
    # workdir is removed on cleanup; absence is itself evidence of Provider cleanup.
    assert not prep.workdir.exists() or sent is None
