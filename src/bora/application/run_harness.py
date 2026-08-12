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
from bora.provider.outcomes import ProcessTerminalKind
from bora.provider.workspace_plan import WorkspacePlan
from bora.runtime.identity import AttemptIdentity, IdentityFactory


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


def _worker_env(*, agent_service_sock: str | None) -> dict[str, str]:
    """Least-privilege env projection for the production worker."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": os.pathsep.join(p for p in sys.path if p and not p.endswith("zip")),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C"),
    }
    from bora.runtime.offline import DEFAULT_OFFLINE_ENV, is_offline_agent

    # Codex/login may need user config; keep only when not offline.
    if not is_offline_agent():
        for key in ("CODEX_HOME", "OPENAI_API_KEY", "TERM"):
            if key in os.environ:
                env[key] = os.environ[key]
    if agent_service_sock:
        env["BORA_AGENT_SERVICE_SOCK"] = agent_service_sock
    # Never allow unit stubs on production public path.
    env.pop("BORA_SDK_SESSION_STUB", None)
    # Propagate offline fail-closed flag into the worker (SDK session path).
    if is_offline_agent():
        env[DEFAULT_OFFLINE_ENV] = "1"
    return env


async def run_harness_package(
    lock: LockedTaskConfig,
    package_root: Path,
    *,
    identity_factory: IdentityFactory | None = None,
    timeout_seconds: float = 30.0,
    artifact_hold_dir: Path | None = None,
    agent_service_sock: str | None = None,
    attempt: AttemptIdentity | None = None,
    workspace_root: Path | None = None,
    database_root: Path | None = None,
) -> dict[str, Any]:
    """Start task worker under L0 Provider and return terminal envelope.

    Published artifact files are copied into *artifact_hold_dir* (or a returned
    temp directory retained via the ``_hold`` key) so callers can evaluate after
    the worker exits.

    When *attempt* is provided (e.g. the same Runtime-owned Attempt used by
    ParentAgentService), the worker scope reuses that identity chain instead of
    minting a second, divergent Attempt.

    *workspace_root* defaults to *package_root*. L1 SDK path may point it at the
    Attempt host workspace so harness can read agent-written files.

    *database_root* is the Database root (optional). When set, the worker injects
    ``[task_dir, database_root]`` on ``sys.path`` so authors import ``shared.lib.*``
    / ``lib.*`` and can resolve code-path assets under the Dataset (#68).
    """
    factory = identity_factory or IdentityFactory()
    if attempt is not None:
        trial = attempt.trial
        run = trial.run
    else:
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

        ws_root = (workspace_root or package_root).resolve()
        db_root = database_root.resolve() if database_root is not None else None
        launch = {
            "package_root": str(package_root.resolve()),
            "workspace_root": str(ws_root),
            "entrypoint": str(thaw(lock.harness).get("entrypoint", "harness:run")),
            "params": thaw(lock.parameters),
            "attempt_id": attempt.value,
            "trial_id": trial.value,
            "run_id": run.value,
            "artifact_dir": str(artifact_dir),
        }
        if db_root is not None:
            launch["database_root"] = str(db_root)

        provider = LocalProcessProvider()
        plan = ProcessLaunchPlan(
            attempt=attempt,
            workspace=WorkspacePlan(attempt=attempt, base_dir=work_base, relative_workdir="ws"),
            executable=ExecutableGrant(path=Path(sys.executable)),
            argv=(sys.executable, "-m", "bora.runtime.task_worker", "--fd", str(child_fd)),
            env=_worker_env(agent_service_sock=agent_service_sock),
            timeout_seconds=timeout_seconds,
            pass_fds=(child_fd,),
        )

        try:
            # Launch JSON must land in the socket buffer before the worker reads.
            _send(parent, launch)
            parent.settimeout(timeout_seconds)
            loop = asyncio.get_running_loop()

            def _recv_or_fail() -> dict[str, Any]:
                try:
                    return _recv(parent)
                except Exception as exc:
                    return {"ok": False, "error": type(exc).__name__, "message": str(exc)}

            # Envelope must arrive before/while the worker runs — never wait for
            # execute() to finish before receiving.
            outcome, envelope = await asyncio.gather(
                provider.execute(plan),
                loop.run_in_executor(None, _recv_or_fail),
            )

            stderr_text = outcome.stderr_summary or ""
            if not envelope.get("ok") and stderr_text:
                envelope["stderr"] = stderr_text[-2000:]
            if outcome.terminal == ProcessTerminalKind.TIMED_OUT and envelope.get("ok"):
                # Process supervision timed out after a terminal was already sent.
                envelope["timed_out"] = True

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
                "worker_exit": outcome.exit_code,
                "parent_imported_task": any("bora_task_harness" in m for m in sys.modules),
                "artifact_hold": str(hold),
                "writer_stop_confirmed": outcome.writer_stop_confirmed,
                "pgid": outcome.pgid,
                "process_terminal": outcome.terminal.value,
            }
        finally:
            parent.close()
            child.close()
