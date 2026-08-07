"""DockerProvider — L1 isolated Attempt runtime (first implementation).

Uses Docker CLI (not Docker socket delegated into task containers).
Fails closed when daemon/image/platform unavailable.

Multi-actor support: long-lived ExecutionTargets with numeric UID/HOME and
``docker exec`` (never host CLI fallback on L1 agent path).
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from bora.adapters.provider_docker.errors import ProviderL1Error
from bora.adapters.provider_docker.multi_actor import DockerMultiActorMixin
from bora.adapters.provider_docker.package_view import copy_package_filtered
from bora.adapters.provider_docker.types import DockerImageLock, DockerRuntime
from bora.provider.errors import ERROR_SPAWN_FAILED
from bora.provider.outcomes import ProcessOutcome, ProcessTerminalKind
from bora.runtime.identity import AttemptIdentity


class DockerProvider(DockerMultiActorMixin):
    """Minimal L1 Docker Provider: prepare / run / stop / cleanup."""

    def __init__(self, *, image_lock_path: Path | None = None) -> None:
        self._image_lock_path = image_lock_path or Path(".bora/runtime-images/provider-l1.json")

    def preflight(self) -> None:
        if not self._docker_ok():
            raise ProviderL1Error(
                "provider_l1_unavailable",
                "Docker daemon unavailable",
            )
        if not self._image_lock_path.is_file():
            raise ProviderL1Error(
                "image_unresolved",
                f"missing image lock: {self._image_lock_path}",
            )

    def prepare(
        self,
        attempt: AttemptIdentity,
        *,
        package_root: Path,
        work_root: Path,
        network_mode: str = "none",
        read_only_package: bool = True,
        hide_evaluation: bool = True,
        image_lock: DockerImageLock | None = None,
    ) -> DockerRuntime:
        if image_lock is None:
            self.preflight()
            lock = DockerImageLock.load(self._image_lock_path)
        else:
            if not self._docker_ok():
                raise ProviderL1Error(
                    "provider_l1_unavailable",
                    "Docker daemon unavailable",
                )
            lock = image_lock
        work_root.mkdir(parents=True, exist_ok=True)
        workspace = work_root / "workspace"
        artifacts = work_root / "artifacts"
        workspace.mkdir(exist_ok=True)
        artifacts.mkdir(exist_ok=True)

        # Create Attempt-scoped network when not fully offline.
        network_id: str | None = None
        if network_mode != "none":
            network_id = self._create_network(attempt)

        runtime = DockerRuntime(
            attempt=attempt,
            network_id=network_id,
            image_lock=lock,
            workdir_host=work_root,
            package_host=package_root.resolve(),
            policy_digests={
                "network_mode": network_mode,
                "package_ro": str(read_only_package),
                "hide_evaluation": str(hide_evaluation),
            },
        )
        return runtime

    def run_command(
        self,
        runtime: DockerRuntime,
        argv: list[str],
        *,
        timeout_seconds: float = 120.0,
        env: dict[str, str] | None = None,
        network: bool = False,
        network_mode: str | None = None,
        mounts: list[tuple[str, str, str]] | None = None,
        include_package: bool = True,
        include_workspace: bool = True,
        user: str = "10001:10001",
        writer_name: str = "container",
        workdir: str = "/attempt/workspace",
        read_only_root: bool = True,
        stream_dir: Path | None = None,
    ) -> ProcessOutcome:
        """Run argv inside a new container; reap and return L1 outcome facts.

        When ``stream_dir`` is set, full stdout/stderr are written there
        (``stdout.txt`` / ``stderr.txt``) before summary truncation.
        """
        if runtime.cleaned:
            raise ProviderL1Error("already_cleaned", "runtime cleaned")
        if runtime.image_lock is None or runtime.package_host is None:
            raise ProviderL1Error("invalid_plan", "runtime not prepared")

        runtime.register_writer(writer_name)
        name = f"bora-{runtime.attempt.value[-12:]}-{uuid.uuid4().hex[:8]}"
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--user",
            user,
            "--security-opt",
            "no-new-privileges",
        ]
        if read_only_root:
            cmd.extend(["--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m"])
        # Network: default none. bridge = agent provider egress (declared).
        # internal network_id only when network=True and mode not bridge.
        mode = network_mode or ("bridge" if network and runtime.network_id is None else None)
        if mode == "bridge":
            cmd.extend(["--network", "bridge"])
        elif network and runtime.network_id is not None:
            cmd.extend(["--network", runtime.network_id])
        else:
            cmd.extend(["--network", "none"])

        # Package mount: filtered tree without evaluation/ when hide_evaluation.
        if include_package and runtime.workdir_host is not None:
            package_mount = runtime.package_host
            if runtime.policy_digests.get("hide_evaluation") == "True":
                filtered = runtime.workdir_host / "package_view"
                if not filtered.exists():
                    copy_package_filtered(runtime.package_host, filtered)
                package_mount = filtered
            cmd.extend(["-v", f"{package_mount}:/attempt/package:ro"])
        if include_workspace and runtime.workdir_host is not None:
            cmd.extend(
                [
                    "-v",
                    f"{runtime.workdir_host}/workspace:/attempt/workspace:rw",
                    "-v",
                    f"{runtime.workdir_host}/artifacts:/attempt/artifacts:rw",
                ]
            )
        if mounts:
            for src, dst, mode_m in mounts:
                cmd.extend(["-v", f"{src}:{dst}:{mode_m}"])

        # Never mount Docker socket / never pass DOCKER_* to task.
        for key, val in (env or {}).items():
            if key.upper() in {"DOCKER_HOST", "DOCKER_SOCK"}:
                continue
            cmd.extend(["-e", f"{key}={val}"])

        cmd.extend(["--workdir", workdir, runtime.image_lock.image_tag, *argv])

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            runtime.termination_actions.append("timeout_kill")
            kill = subprocess.run(
                ["docker", "rm", "-f", name], check=False, capture_output=True, text=True
            )
            # Only confirm stop if the named container is gone.
            gone = (
                subprocess.run(
                    ["docker", "inspect", name],
                    check=False,
                    capture_output=True,
                ).returncode
                != 0
            )
            confirmed = gone and kill.returncode == 0
            runtime.record_writer_stop(confirmed)
            return ProcessOutcome(
                attempt=runtime.attempt,
                assurance="l0",  # single-container probe; not full L1 Attempt isolation
                terminal=ProcessTerminalKind.TIMED_OUT,
                exit_code=None,
                signal=None,
                stdout_summary="",
                stderr_summary="timeout",
                truncated=False,
                pid=None,
                pgid=None,
                termination_actions=tuple(runtime.termination_actions),
                writer_stop_confirmed=runtime.writer_stop_confirmed,
                cleanup_ok=True,
                cleanup_warning=None
                if runtime.writer_stop_confirmed
                else "writer_stop: unconfirmed after timeout kill",
            )
        except OSError as exc:
            raise ProviderL1Error(ERROR_SPAWN_FAILED, f"docker run failed: {exc}") from exc

        # docker run --rm waits for main process exit → writer stop confirmed.
        runtime.record_writer_stop(proc.returncode is not None)
        terminal = (
            ProcessTerminalKind.EXITED
            if proc.returncode is not None
            else ProcessTerminalKind.KILLED
        )
        full_out = proc.stdout or ""
        full_err = proc.stderr or ""
        if stream_dir is not None:
            stream_dir.mkdir(parents=True, exist_ok=True)
            (stream_dir / "stdout.txt").write_text(full_out, encoding="utf-8")
            (stream_dir / "stderr.txt").write_text(full_err, encoding="utf-8")
        return ProcessOutcome(
            attempt=runtime.attempt,
            assurance="l0",
            terminal=terminal,
            exit_code=proc.returncode,
            signal=None,
            stdout_summary=full_out[-8000:],
            stderr_summary=full_err[-8000:],
            truncated=len(full_out) > 8000 or len(full_err) > 8000,
            pid=None,
            pgid=None,
            termination_actions=tuple(runtime.termination_actions),
            writer_stop_confirmed=runtime.writer_stop_confirmed,
            cleanup_ok=True,
            detail={
                "image": runtime.image_lock.image_digest if runtime.image_lock else "",
                "platform": runtime.image_lock.platform if runtime.image_lock else "",
                "containment": "single_container_probe",
                "writer": writer_name,
                **({"stream_dir": str(stream_dir)} if stream_dir is not None else {}),
            },
        )

    def cleanup(self, runtime: DockerRuntime) -> None:
        if runtime.cleaned:
            return
        self.stop_agent_targets(runtime)
        if runtime.network_id:
            subprocess.run(
                ["docker", "network", "rm", runtime.network_id],
                check=False,
                capture_output=True,
            )
        runtime.cleaned = True
        # Do not force writer_stop_confirmed; leave last probe fact intact.

    @staticmethod
    def _docker_ok() -> bool:
        try:
            proc = subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _create_network(attempt: AttemptIdentity) -> str:
        """Create Attempt-scoped internal network; fail closed (no non-internal fallback)."""
        name = f"bora-net-{attempt.value[-16:]}"
        proc = subprocess.run(
            ["docker", "network", "create", "--internal", name],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise ProviderL1Error(
                "network_projection_denied",
                f"cannot create internal network: {proc.stderr or proc.stdout}",
            )
        return (proc.stdout or name).strip() or name
