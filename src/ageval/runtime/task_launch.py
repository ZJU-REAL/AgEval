"""Run the task's own ``run.py`` in a child process of the control plane.

The task drives its Agent session and publishes artifacts; it never touches the
box. That is why the worker is a child here rather than a process inside the
Attempt's box: the Agent is what runs in the box, reached over the Agent Service
socket, and the same arrangement works whether the box is this machine, a
container, or a sandbox on someone else's.

The channel is length-prefixed JSON over the child's own pipes: one launch
message in, one result envelope out.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import struct
import sys
from pathlib import Path
from typing import Any

from ageval.attempt.ctx import AttemptCtx
from ageval.config.model import thaw
from ageval.environments.protocol import WORKSPACE_PATH
from ageval.runtime.offline import DEFAULT_OFFLINE_ENV, is_offline_agent

WORKER_MODULE = "ageval.runtime.task_worker"
# stderr is diagnostics; keep the tail that fits in one evidence fact.
_STDERR_TAIL_BYTES = 4000


async def launch_task_worker(ctx: AttemptCtx) -> dict[str, Any]:
    """Run the task entrypoint and return its result envelope."""
    workspace = _worker_workspace(ctx)
    artifacts = ctx.evidence.path("task-artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        WORKER_MODULE,
        cwd=str(workspace),
        env=_worker_env(ctx, workspace=workspace, artifacts=artifacts),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdin is not None
    process.stdin.write(_frame(_launch_message(ctx)))
    await process.stdin.drain()
    process.stdin.close()

    envelope = await _collect(process, timeout=ctx.remaining_seconds())
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


def _worker_workspace(ctx: AttemptCtx) -> Path:
    """The directory ``run.py`` sees as the workspace.

    Seed is uploaded into the box. When this machine can see that directory
    (local, docker bind-mount), the worker must look there — a parallel empty
    evidence folder is not the workspace. Remote kinds without a shared
    filesystem keep a host-side copy of the seed so ``run.py`` can still read
    instruction files.
    """
    host_path = getattr(ctx.host, "host_path", None)
    if callable(host_path):
        return Path(host_path(WORKSPACE_PATH))
    workspace = ctx.evidence.path("task-workspace")
    seed = ctx.seed_dir
    if seed is not None and seed.is_dir():
        _copy_seed(seed, workspace)
    return workspace


def _copy_seed(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        target = dest / path.name
        if path.is_dir():
            shutil.copytree(path, target, dirs_exist_ok=True)
        else:
            shutil.copy2(path, target)


def _worker_env(ctx: AttemptCtx, *, workspace: Path, artifacts: Path) -> dict[str, str]:
    """Least privilege: where to write, whom to call, and nothing else."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": os.pathsep.join(p for p in sys.path if p and not p.endswith(".zip")),
        "PYTHONUNBUFFERED": "1",
        "LANG": os.environ.get("LANG", "C"),
        "AGEVAL_ATTEMPT_ID": ctx.attempt_id,
        "AGEVAL_WORKSPACE": str(workspace),
        "AGEVAL_ARTIFACTS": str(artifacts),
    }
    if ctx.agent_service is not None:
        env["AGEVAL_AGENT_SERVICE_SOCK"] = str(ctx.agent_service.socket_path)
    if is_offline_agent():
        env[DEFAULT_OFFLINE_ENV] = "1"
    return env


async def _collect(
    process: asyncio.subprocess.Process,
    *,
    timeout: float | None,
) -> dict[str, Any]:
    """Read the envelope, keep the stderr tail, and reap the child."""
    assert process.stdout is not None
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        return {"ok": False, "error": "task_run_timeout", "exit_code": process.returncode}

    envelope = _parse(stdout)
    envelope["exit_code"] = process.returncode
    tail = stderr.decode("utf-8", errors="replace")[-_STDERR_TAIL_BYTES:]
    if tail:
        envelope["stderr"] = tail
    return envelope


def _parse(stdout: bytes) -> dict[str, Any]:
    if len(stdout) < 4:
        return {"ok": False, "error": "task_worker_no_result"}
    (size,) = struct.unpack("!I", stdout[:4])
    body = stdout[4 : 4 + size]
    if len(body) < size:
        return {"ok": False, "error": "task_worker_truncated_result"}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "error": "task_worker_unreadable_result"}
    return parsed if isinstance(parsed, dict) else {"ok": False, "error": "task_worker_bad_result"}


def _record_artifacts(ctx: AttemptCtx, envelope: dict[str, Any]) -> None:
    """Keep artifact names in evidence; the bytes stay where they were written."""
    published = envelope.get("published")
    if not isinstance(published, dict):
        return
    names = {str(key): os.path.basename(str(value)) for key, value in published.items()}
    envelope["published"] = names
    ctx.record_fact("artifacts_published", {"ids": sorted(names)})


def _frame(obj: dict[str, Any]) -> bytes:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return struct.pack("!I", len(raw)) + raw
