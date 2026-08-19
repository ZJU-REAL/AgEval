"""Attach the task worker inside the box and collect its envelope.

The worker is a process the box starts, not a process the control plane forks:
the only channel is ``attach_stdio``, so the same launch path works for a local
directory box and for a remote one. Agent invocations do not travel here — they
go back over the Agent Service socket named in the worker env.
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
from typing import Any

from ageval.attempt.ctx import AttemptCtx
from ageval.config.model import thaw
from ageval.environments.protocol import StdioTransport
from ageval.runtime.offline import DEFAULT_OFFLINE_ENV, is_offline_agent

WORKER_MODULE = "ageval.runtime.task_worker"
# stderr is diagnostics; keep the tail that fits in one evidence fact.
_STDERR_TAIL_BYTES = 4000


async def launch_task_worker(ctx: AttemptCtx) -> dict[str, Any]:
    """Run the task entrypoint inside the box; return its result envelope."""
    argv = [*ctx.host.python_command, "-m", WORKER_MODULE]
    pipe = await ctx.host.attach_stdio(
        argv,
        placement=ctx.host.placement(),
        env=_worker_env(ctx),
    )
    try:
        _send(pipe, _launch_message(ctx))
        envelope = await _collect(pipe, timeout=ctx.remaining_seconds())
    finally:
        pipe.terminate()
    _record_artifacts(ctx, envelope)
    return envelope


def _launch_message(ctx: AttemptCtx) -> dict[str, Any]:
    references = thaw(ctx.lock.resolved_references)
    return {
        "task_root": str(ctx.task_root),
        "dataset_root": str(ctx.dataset_root),
        "entrypoint": str(references["run_entrypoint"]),
        "params": thaw(ctx.lock.parameters),
        "attempt_id": ctx.attempt_id,
        "trial_id": ctx.trial_id,
        "run_id": ctx.run_id,
    }


def _worker_env(ctx: AttemptCtx) -> dict[str, str]:
    """Least privilege: a socket name, an import path, no host credential."""
    env = {
        "PYTHONPATH": os.pathsep.join(p for p in sys.path if p and not p.endswith(".zip")),
        "PYTHONUNBUFFERED": "1",
        "AGEVAL_ATTEMPT_ID": ctx.attempt_id,
    }
    if ctx.agent_service is not None:
        env["AGEVAL_AGENT_SERVICE_SOCK"] = str(ctx.agent_service.socket_path)
    if is_offline_agent():
        env[DEFAULT_OFFLINE_ENV] = "1"
    return env


async def _collect(pipe: StdioTransport, *, timeout: float | None) -> dict[str, Any]:
    """Read the envelope while draining stderr, then reap the worker."""
    loop = asyncio.get_running_loop()
    stderr_task = loop.run_in_executor(None, _drain, pipe.stderr)
    try:
        envelope = await asyncio.wait_for(loop.run_in_executor(None, _recv, pipe.stdout), timeout)
    except TimeoutError:
        pipe.terminate()
        envelope = {"ok": False, "error": "task_run_timeout"}
    except EOFError as exc:
        envelope = {"ok": False, "error": "task_worker_no_result", "message": str(exc)}
    exit_code = await loop.run_in_executor(None, pipe.wait, 10.0)
    stderr = await stderr_task
    envelope["exit_code"] = exit_code
    if stderr:
        envelope["stderr"] = stderr[-_STDERR_TAIL_BYTES:]
    return envelope


def _record_artifacts(ctx: AttemptCtx, envelope: dict[str, Any]) -> None:
    """Keep artifact names in evidence; the bytes stay in the box."""
    published = envelope.get("published")
    if not isinstance(published, dict):
        return
    names = {str(key): os.path.basename(str(value)) for key, value in published.items()}
    envelope["published"] = names
    ctx.record_fact("artifacts_published", {"ids": sorted(names)})


def _send(pipe: StdioTransport, obj: dict[str, Any]) -> None:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    stdin = pipe.stdin
    assert hasattr(stdin, "write") and hasattr(stdin, "flush")
    stdin.write(struct.pack("!I", len(raw)) + raw)  # type: ignore[attr-defined]
    stdin.flush()  # type: ignore[attr-defined]


def _recv(stdout: Any) -> dict[str, Any]:
    header = _read_exact(stdout, 4)
    (size,) = struct.unpack("!I", header)
    return json.loads(_read_exact(stdout, size).decode("utf-8"))


def _read_exact(stream: Any, size: int) -> bytes:
    buf = b""
    while len(buf) < size:
        chunk = stream.read(size - len(buf))
        if not chunk:
            raise EOFError("worker closed the channel before sending a result")
        buf += chunk
    return buf


def _drain(stream: Any) -> str:
    if stream is None:
        return ""
    return stream.read().decode("utf-8", errors="replace")
