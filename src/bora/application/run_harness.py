"""Application harness checkpoint: L0 Provider launches task worker.

Control Plane does not import package harness modules.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any

from bora.adapters.provider_local import LocalProcessProvider
from bora.config.model import LockedTaskConfig, thaw
from bora.provider.contract import ExecutableGrant, ProcessLaunchPlan
from bora.provider.workspace_plan import WorkspacePlan
from bora.runtime.identity import IdentityFactory


def _send(sock: socket.socket, obj: dict[str, Any]) -> None:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sock.sendall(struct.pack("!I", len(raw)) + raw)


def _recv(sock: socket.socket) -> dict[str, Any]:
    hdr = _read_exact(sock, 4)
    (n,) = struct.unpack("!I", hdr)
    body = _read_exact(sock, n)
    return json.loads(body.decode("utf-8"))


def _read_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise EOFError("socket closed")
        buf += chunk
    return buf


async def run_harness_package(
    lock: LockedTaskConfig,
    package_root: Path,
    *,
    identity_factory: IdentityFactory | None = None,
    timeout_seconds: float = 30.0,
    artifact_hold_dir: Path | None = None,
    agent_service_sock: str | None = None,
) -> dict[str, Any]:
    """Start task worker under L0 Provider and return terminal envelope.

    Published artifact files are copied into *artifact_hold_dir* (or a returned
    temp directory retained via the ``_hold`` key) so callers can evaluate after
    the worker exits.
    """
    factory = identity_factory or IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, lock.digest)
    attempt = factory.new_attempt(trial)

    parent, child = socket.socketpair()
    child_fd = child.fileno()

    hold = artifact_hold_dir or Path(tempfile.mkdtemp(prefix="bora-artifacts-"))
    hold.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bora-harness-") as tmp:
        tmp_path = Path(tmp)
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()
        work_base = tmp_path / "provider"
        work_base.mkdir()

        launch = {
            "package_root": str(package_root.resolve()),
            "entrypoint": str(thaw(lock.harness).get("entrypoint", "harness:run")),
            "params": thaw(lock.parameters),
            "attempt_id": attempt.value,
            "trial_id": trial.value,
            "run_id": run.value,
            "artifact_dir": str(artifact_dir),
        }

        provider = LocalProcessProvider()
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": os.pathsep.join(p for p in sys.path if p and not p.endswith("zip")),
        }
        if agent_service_sock:
            env["BORA_AGENT_SERVICE_SOCK"] = agent_service_sock
        prepared = await provider.prepare(
            ProcessLaunchPlan(
                attempt=attempt,
                workspace=WorkspacePlan(attempt=attempt, base_dir=work_base, relative_workdir="ws"),
                executable=ExecutableGrant(path=Path(sys.executable)),
                argv=(sys.executable, "-m", "bora.runtime.task_worker", "--fd", str(child_fd)),
                env=env,
                timeout_seconds=timeout_seconds,
            )
        )

        # Production worker: least-privilege env projection (not full host dump).
        child_env = {
            "PATH": env.get("PATH", os.environ.get("PATH", "/usr/bin:/bin")),
            "PYTHONPATH": env.get("PYTHONPATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "LANG": os.environ.get("LANG", "C"),
        }
        # Codex/login may need user config; keep only when not offline.
        if os.environ.get("BORA_OFFLINE_AGENT") != "1":
            for key in ("CODEX_HOME", "OPENAI_API_KEY", "TERM"):
                if key in os.environ:
                    child_env[key] = os.environ[key]
        if agent_service_sock:
            child_env["BORA_AGENT_SERVICE_SOCK"] = agent_service_sock
        # Never allow unit stubs on production public path.
        child_env.pop("BORA_SDK_SESSION_STUB", None)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "bora.runtime.task_worker",
            "--fd",
            str(child_fd),
            cwd=str(prepared.workdir),
            env=child_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            pass_fds=(child_fd,),
        )
        child.close()
        try:
            _send(parent, launch)
            parent.settimeout(timeout_seconds)
            loop = asyncio.get_running_loop()

            def _recv_or_fail() -> dict[str, Any]:
                try:
                    return _recv(parent)
                except Exception as exc:
                    return {"ok": False, "error": type(exc).__name__, "message": str(exc)}

            envelope = await loop.run_in_executor(None, _recv_or_fail)
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
            except TimeoutError:
                proc.kill()
                await proc.wait()
            stderr_text = ""
            if proc.stderr is not None:
                stderr_text = (await proc.stderr.read()).decode("utf-8", errors="replace")
            if not envelope.get("ok") and stderr_text:
                envelope["stderr"] = stderr_text[-2000:]

            # Copy published artifacts to durable hold dir before temp cleanup.
            published = dict(envelope.get("published") or {})
            durable: dict[str, str] = {}
            for art_id, src in published.items():
                src_path = Path(str(src))
                if src_path.is_file():
                    dest = hold / f"{art_id}{src_path.suffix or '.json'}"
                    shutil.copy2(src_path, dest)
                    durable[str(art_id)] = str(dest)
            envelope["published"] = durable

            return {
                "attempt": attempt.value,
                "envelope": envelope,
                "worker_exit": proc.returncode,
                "parent_imported_task": any("bora_task_harness" in m for m in sys.modules),
                "artifact_hold": str(hold),
            }
        finally:
            parent.close()
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            prepared.process = proc  # type: ignore[assignment]
            prepared.pgid = None
            await provider.cleanup(prepared)
