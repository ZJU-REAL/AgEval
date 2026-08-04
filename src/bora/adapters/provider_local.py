"""LocalProcessProvider — real POSIX local subprocess with process-group cleanup.

assurance: l0 only. No shell=True, no undeclared env, no Docker claims.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from bora.provider.contract import ProcessLaunchPlan
from bora.provider.errors import (
    ERROR_ALREADY_CLEANED,
    ERROR_CROSS_ATTEMPT,
    ERROR_SPAWN_FAILED,
    ProviderError,
)
from bora.provider.outcomes import ProcessOutcome, ProcessTerminalKind
from bora.runtime.cancellation import CancellationSignal
from bora.runtime.identity import AttemptIdentity


@dataclass
class PreparedLocalRuntime:
    """Handle for a prepared/running L0 process bound to one Attempt."""

    attempt: AttemptIdentity
    workdir: Path
    plan: ProcessLaunchPlan
    process: asyncio.subprocess.Process | None = None
    pgid: int | None = None
    cleaned: bool = False
    stdout_buf: bytearray = field(default_factory=bytearray)
    stderr_buf: bytearray = field(default_factory=bytearray)
    truncated: bool = False
    termination_actions: list[str] = field(default_factory=list)
    writer_stop_confirmed: bool = False


class LocalProcessProvider:
    """L0 local process provider (POSIX: new session / process group)."""

    def __init__(
        self,
        *,
        term_wait_seconds: float = 0.3,
        kill_wait_seconds: float = 0.5,
    ) -> None:
        self._term_wait = term_wait_seconds
        self._kill_wait = kill_wait_seconds

    async def prepare(self, plan: ProcessLaunchPlan) -> PreparedLocalRuntime:
        """Validate plan and create Provider-owned workdir."""
        workdir = plan.workspace.resolve_workdir()
        workdir.mkdir(parents=True, exist_ok=True)
        plan.executable.resolve()
        return PreparedLocalRuntime(
            attempt=plan.attempt,
            workdir=workdir,
            plan=plan,
        )

    async def start(self, prepared: PreparedLocalRuntime) -> PreparedLocalRuntime:
        """Spawn direct child in a new session (own process group)."""
        self._assert_handle(prepared)
        if prepared.process is not None:
            raise ProviderError(ERROR_SPAWN_FAILED, "process already started")
        plan = prepared.plan
        exe = plan.executable.resolve()
        argv = [str(exe), *plan.argv[1:]] if plan.argv else [str(exe)]
        # Prefer plan.argv as full argv when argv[0] matches basename or path.
        if plan.argv:
            argv = list(plan.argv)
            # Ensure argv[0] is the granted executable path.
            argv[0] = str(exe)

        env = {str(k): str(v) for k, v in plan.env.items()}
        # Minimal required env for child (PATH for dynamic linkers / python).
        if "PATH" not in env:
            env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
        if "HOME" not in env:
            env["HOME"] = os.environ.get("HOME", prepared.workdir.as_posix())

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(prepared.workdir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,  # new process group on POSIX
            )
        except OSError as exc:
            raise ProviderError(ERROR_SPAWN_FAILED, f"spawn failed: {exc}") from exc

        prepared.process = process
        try:
            prepared.pgid = os.getpgid(process.pid)
        except OSError:
            prepared.pgid = process.pid
        return prepared

    async def wait(
        self,
        prepared: PreparedLocalRuntime,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> ProcessOutcome:
        """Wait for exit, timeout, or cancel; then cleanup-once."""
        self._assert_handle(prepared)
        process = prepared.process
        if process is None:
            return await self._finish(
                prepared,
                terminal=ProcessTerminalKind.SPAWN_FAILED,
                exit_code=None,
                signal_num=None,
            )

        plan = prepared.plan
        drain_task = asyncio.create_task(self._drain_streams(prepared))
        start = time.monotonic()
        timeout = plan.timeout_seconds
        terminal = ProcessTerminalKind.EXITED
        exit_code: int | None = None
        signal_num: int | None = None

        try:
            while True:
                if cancellation is not None and cancellation.is_cancelled:
                    terminal = ProcessTerminalKind.CANCELLED
                    await self._terminate_group(prepared)
                    break
                if timeout is not None and (time.monotonic() - start) >= timeout:
                    terminal = ProcessTerminalKind.TIMED_OUT
                    await self._terminate_group(prepared)
                    break
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.05)
                    exit_code = process.returncode
                    if exit_code is not None and exit_code < 0:
                        signal_num = -exit_code
                        terminal = ProcessTerminalKind.KILLED
                    else:
                        terminal = ProcessTerminalKind.EXITED
                    break
                except TimeoutError:
                    continue
        finally:
            # Ensure process is reaped and streams drained.
            if process.returncode is None:
                await self._terminate_group(prepared)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=self._kill_wait + 1)
                exit_code = process.returncode
            await drain_task

        # Residual same-group cleanup after normal exit.
        if prepared.pgid is not None:
            await self._ensure_group_dead(prepared)

        return await self._finish(
            prepared,
            terminal=terminal,
            exit_code=exit_code,
            signal_num=signal_num,
        )

    async def cleanup(self, prepared: PreparedLocalRuntime) -> None:
        """Idempotent cleanup: kill group if needed, remove owned workdir.

        Does **not** force ``writer_stop_confirmed=True``. That flag is set only
        from group-liveness probes in ``_terminate_group`` / ``_ensure_group_dead``.
        """
        if prepared.cleaned:
            return
        if prepared.process is not None and prepared.process.returncode is None:
            await self._terminate_group(prepared)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(prepared.process.wait(), timeout=self._kill_wait + 1)
        if prepared.pgid is not None:
            await self._ensure_group_dead(prepared)
        elif prepared.process is not None and prepared.process.returncode is not None:
            # Direct child exited and no pgid tracking — treat as stopped.
            prepared.writer_stop_confirmed = True
        # Remove only the Attempt workdir we created.
        workdir = prepared.workdir
        if workdir.exists():
            # Best-effort recursive delete of Provider-owned workdir only.
            import shutil

            shutil.rmtree(workdir, ignore_errors=True)
        prepared.cleaned = True

    async def _finish(
        self,
        prepared: PreparedLocalRuntime,
        *,
        terminal: ProcessTerminalKind,
        exit_code: int | None,
        signal_num: int | None,
    ) -> ProcessOutcome:
        warning: str | None = None
        try:
            await self.cleanup(prepared)
            cleanup_ok = True
        except Exception as exc:  # noqa: BLE001
            cleanup_ok = False
            warning = f"cleanup failed: {type(exc).__name__}"

        # Unconfirmed writer stop is a cleanup warning, not a silent true.
        if not prepared.writer_stop_confirmed:
            stop_warn = "writer_stop: unconfirmed after TERM/KILL wait"
            warning = f"{warning}; {stop_warn}" if warning else stop_warn

        max_b = prepared.plan.max_stream_bytes
        stdout = bytes(prepared.stdout_buf[:max_b]).decode("utf-8", errors="replace")
        stderr = bytes(prepared.stderr_buf[:max_b]).decode("utf-8", errors="replace")
        return ProcessOutcome(
            attempt=prepared.attempt,
            assurance="l0",
            terminal=terminal,
            exit_code=exit_code,
            signal=signal_num,
            stdout_summary=stdout,
            stderr_summary=stderr,
            truncated=prepared.truncated,
            pid=prepared.process.pid if prepared.process else None,
            pgid=prepared.pgid,
            termination_actions=tuple(prepared.termination_actions),
            writer_stop_confirmed=prepared.writer_stop_confirmed,
            cleanup_ok=cleanup_ok,
            cleanup_warning=warning,
        )

    async def _drain_streams(self, prepared: PreparedLocalRuntime) -> None:
        process = prepared.process
        if process is None:
            return
        max_b = prepared.plan.max_stream_bytes

        async def read(stream: asyncio.StreamReader | None, buf: bytearray) -> None:
            if stream is None:
                return
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                room = max_b - len(buf)
                if room <= 0:
                    prepared.truncated = True
                    # Keep draining to avoid blocking child.
                    continue
                if len(chunk) > room:
                    buf.extend(chunk[:room])
                    prepared.truncated = True
                else:
                    buf.extend(chunk)

        await asyncio.gather(
            read(process.stdout, prepared.stdout_buf),
            read(process.stderr, prepared.stderr_buf),
        )

    async def _terminate_group(self, prepared: PreparedLocalRuntime) -> None:
        pgid = prepared.pgid
        if pgid is None:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
            prepared.termination_actions.append("SIGTERM")
        except ProcessLookupError:
            prepared.writer_stop_confirmed = True
            return
        await asyncio.sleep(self._term_wait)
        if self._group_alive(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
                prepared.termination_actions.append("SIGKILL")
            except ProcessLookupError:
                pass
            await asyncio.sleep(self._kill_wait)
        prepared.writer_stop_confirmed = not self._group_alive(pgid)

    async def _ensure_group_dead(self, prepared: PreparedLocalRuntime) -> None:
        pgid = prepared.pgid
        if pgid is None:
            prepared.writer_stop_confirmed = True
            return
        if self._group_alive(pgid):
            await self._terminate_group(prepared)
        else:
            prepared.writer_stop_confirmed = True

    @staticmethod
    def _group_alive(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Exists but not owned — treat as still live.
            return True

    @staticmethod
    def _assert_handle(prepared: PreparedLocalRuntime) -> None:
        if prepared.cleaned:
            raise ProviderError(ERROR_ALREADY_CLEANED, "runtime already cleaned")
        if prepared.attempt != prepared.plan.attempt:
            raise ProviderError(ERROR_CROSS_ATTEMPT, "handle attempt mismatch")
