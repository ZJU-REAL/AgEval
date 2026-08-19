"""Launch the task worker as a child process and collect its envelope.

The control plane never imports task modules: ``run.py`` is loaded by the child.
The only channel back is a socketpair carrying one launch message and one result
envelope, plus the Agent Service socket for invocations.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import struct
import sys
from pathlib import Path
from typing import Any

from ageval.attempt.ctx import AttemptCtx
from ageval.config.model import thaw

_ENVELOPE_TIMEOUT_SLACK = 5.0


async def launch_task_worker(ctx: AttemptCtx) -> dict[str, Any]:
    """Run the task entrypoint in a child process; return its envelope."""
    scratch = ctx.evidence.path("task-scratch")
    artifacts = ctx.evidence.path("task-artifacts")
    scratch.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    launch = {
        "task_root": str(ctx.task_root),
        "dataset_root": str(ctx.dataset_root),
        "entrypoint": str(thaw(ctx.lock.resolved_references).get("run_entrypoint") or "run:run"),
        "params": thaw(ctx.lock.parameters),
        "attempt_id": ctx.attempt_id,
        "trial_id": ctx.trial_id,
        "run_id": ctx.run_id,
        "workspace_root": str(scratch),
        "artifact_dir": str(artifacts),
    }

    parent, child = socket.socketpair()
    try:
        _send(parent, launch)
        timeout = ctx.remaining_seconds()
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "ageval.runtime.task_worker",
            "--fd",
            str(child.fileno()),
            cwd=str(scratch),
            env=_worker_env(ctx),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            pass_fds=(child.fileno(),),
        )
        loop = asyncio.get_running_loop()
        envelope_task = loop.run_in_executor(None, _recv_or_error, parent, timeout)
        stdout, stderr = await process.communicate()
        envelope = await envelope_task
        envelope.setdefault("exit_code", process.returncode)
        if not envelope.get("ok") and stderr:
            envelope["stderr"] = stderr.decode("utf-8", errors="replace")[-2000:]
        if stdout:
            envelope["stdout"] = stdout.decode("utf-8", errors="replace")[-2000:]
        _publish_artifacts(ctx, envelope, artifacts)
        return envelope
    finally:
        parent.close()
        child.close()


def _publish_artifacts(ctx: AttemptCtx, envelope: dict[str, Any], artifacts: Path) -> None:
    """Record which declared artifacts the task actually produced."""
    published = envelope.get("published")
    if not isinstance(published, dict):
        return
    envelope["published"] = {str(key): Path(str(value)).name for key, value in published.items()}
    ctx.record_fact(
        "artifacts_published",
        {"ids": sorted(envelope["published"]), "dir": artifacts.name},
    )


def _worker_env(ctx: AttemptCtx) -> dict[str, str]:
    """Least-privilege env for the worker: no host credentials pass through."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": os.pathsep.join(p for p in sys.path if p and not p.endswith("zip")),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C"),
        "AGEVAL_ATTEMPT_ID": ctx.attempt_id,
    }
    sock = getattr(ctx.agent_service, "socket_path", None)
    if sock:
        env["AGEVAL_AGENT_SERVICE_SOCK"] = str(sock)
    from ageval.runtime.offline import DEFAULT_OFFLINE_ENV, is_offline_agent

    if is_offline_agent():
        env[DEFAULT_OFFLINE_ENV] = "1"
    return env


def _send(sock: socket.socket, obj: dict[str, Any]) -> None:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sock.sendall(struct.pack("!I", len(raw)) + raw)


def _recv_or_error(sock: socket.socket, timeout: float | None) -> dict[str, Any]:
    sock.settimeout((timeout or 0) + _ENVELOPE_TIMEOUT_SLACK if timeout else None)
    try:
        header = _read_exact(sock, 4)
        (size,) = struct.unpack("!I", header)
        body = _read_exact(sock, size)
        return json.loads(body.decode("utf-8"))
    except (OSError, EOFError, ValueError) as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def _read_exact(sock: socket.socket, size: int) -> bytes:
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise EOFError("task worker closed the channel")
        buf += chunk
    return buf
