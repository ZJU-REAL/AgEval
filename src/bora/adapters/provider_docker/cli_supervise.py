"""Supervise host-side ``docker`` CLI via LocalProcessProvider.execute_sync.

The Attempt sandbox is the container; this helper only wraps the host CLI
client so timeout / teardown / outcome assembly stay in one place.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from bora.adapters.provider_local import LocalProcessProvider
from bora.provider.contract import ExecutableGrant, ProcessLaunchPlan, TerminationPolicy
from bora.provider.outcomes import ProcessOutcome
from bora.provider.workspace_plan import WorkspacePlan
from bora.runtime.identity import AttemptIdentity, IdentityFactory

# Historical subprocess.run(capture_output=True) kept full streams in memory.
# Cap high enough that stream_dir dumps are not silently truncated.
DEFAULT_DOCKER_STREAM_BYTES = 64_000_000


def resolve_docker_executable() -> Path:
    path = shutil.which("docker")
    if not path:
        raise FileNotFoundError("docker executable not found on PATH")
    return Path(path)


def _docker_cli_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    # Host control-plane CLI (not Attempt sandbox projection).
    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    env.pop("BORA_SDK_SESSION_STUB", None)
    if extra:
        env.update(extra)
    return env


def supervise_docker_cli(
    argv: list[str] | tuple[str, ...],
    *,
    timeout_seconds: float,
    attempt: AttemptIdentity | None = None,
    env: dict[str, str] | None = None,
    stdin_bytes: bytes | None = None,
    termination: TerminationPolicy | None = None,
    max_stream_bytes: int = DEFAULT_DOCKER_STREAM_BYTES,
) -> ProcessOutcome:
    """Run a host ``docker …`` argv under LocalProcessProvider supervision."""
    docker = resolve_docker_executable()
    if attempt is None:
        factory = IdentityFactory()
        run = factory.new_run()
        trial = factory.new_trial(run, "sha256:" + "d" * 64)
        attempt = factory.new_attempt(trial)
    args = list(argv)
    if not args or Path(args[0]).name != "docker":
        args = [str(docker), *args]
    else:
        args[0] = str(docker)
    with tempfile.TemporaryDirectory(prefix="bora-docker-cli-") as tmp:
        base = Path(tmp)
        plan = ProcessLaunchPlan(
            attempt=attempt,
            workspace=WorkspacePlan(attempt=attempt, base_dir=base, relative_workdir="ws"),
            executable=ExecutableGrant(path=docker),
            argv=tuple(args),
            env=_docker_cli_env(env),
            timeout_seconds=timeout_seconds,
            max_stream_bytes=max_stream_bytes,
            stdin_bytes=stdin_bytes,
        )
        return LocalProcessProvider().execute_sync(plan, termination=termination)
