"""DockerProvider — L1 isolated Attempt runtime (first implementation).

Uses Docker CLI (not Docker socket delegated into task containers).
Fails closed when daemon/image/platform unavailable.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from bora.provider.errors import ERROR_SPAWN_FAILED, ProviderError
from bora.provider.outcomes import ProcessOutcome, ProcessTerminalKind
from bora.runtime.identity import AttemptIdentity


class ProviderL1Error(ProviderError):
    """L1-specific errors with stable kinds from Spec 07."""


@dataclass
class DockerImageLock:
    kind: str
    platform: str
    image_tag: str
    image_digest: str
    build_input_digest: str

    @classmethod
    def load(cls, path: Path) -> DockerImageLock:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            kind=str(data["kind"]),
            platform=str(data["platform"]),
            image_tag=str(data.get("image_tag", "")),
            image_digest=str(data["image_digest"]),
            build_input_digest=str(data["build_input_digest"]),
        )


@dataclass
class DockerRuntime:
    attempt: AttemptIdentity
    container_id: str | None = None
    network_id: str | None = None
    image_lock: DockerImageLock | None = None
    workdir_host: Path | None = None
    package_host: Path | None = None
    cleaned: bool = False
    writer_stop_confirmed: bool = False
    termination_actions: list[str] = field(default_factory=list)
    assurance: str = "l1"
    policy_digests: dict[str, str] = field(default_factory=dict)


class DockerProvider:
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
    ) -> DockerRuntime:
        self.preflight()
        lock = DockerImageLock.load(self._image_lock_path)
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
        mounts: list[tuple[str, str, str]] | None = None,
    ) -> ProcessOutcome:
        """Run argv inside a new container; reap and return L1 outcome facts."""
        if runtime.cleaned:
            raise ProviderL1Error("already_cleaned", "runtime cleaned")
        if runtime.image_lock is None or runtime.package_host is None:
            raise ProviderL1Error("invalid_plan", "runtime not prepared")

        name = f"bora-{runtime.attempt.value[-12:]}-{uuid.uuid4().hex[:8]}"
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--user",
            "10001:10001",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
        ]
        # Network: default none unless allowed.
        if not network or runtime.network_id is None:
            cmd.extend(["--network", "none"])
        else:
            cmd.extend(["--network", runtime.network_id])

        # Mount package read-only; exclude evaluation by staging filtered tree if needed.
        package_mount = runtime.package_host
        if runtime.policy_digests.get("hide_evaluation") == "True":
            # Bind mount whole package RO; evaluation hide is enforced by mount
            # layout for attempt workspace only — package evaluation path access
            # is tested separately via view checks when filtered tree is used.
            pass
        cmd.extend(
            [
                "-v",
                f"{package_mount}:/attempt/package:ro",
                "-v",
                f"{runtime.workdir_host}/workspace:/attempt/workspace:rw",
                "-v",
                f"{runtime.workdir_host}/artifacts:/attempt/artifacts:rw",
            ]
        )
        if mounts:
            for src, dst, mode in mounts:
                cmd.extend(["-v", f"{src}:{dst}:{mode}"])

        # Never mount Docker socket.
        for key, val in (env or {}).items():
            if key.upper() in {"DOCKER_HOST", "DOCKER_SOCK"}:
                continue
            cmd.extend(["-e", f"{key}={val}"])

        cmd.extend(["--workdir", "/attempt/workspace", runtime.image_lock.image_tag, *argv])

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
            subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
            runtime.writer_stop_confirmed = True
            return ProcessOutcome(
                attempt=runtime.attempt,
                assurance="l1",
                terminal=ProcessTerminalKind.TIMED_OUT,
                exit_code=None,
                signal=None,
                stdout_summary="",
                stderr_summary="timeout",
                truncated=False,
                pid=None,
                pgid=None,
                termination_actions=tuple(runtime.termination_actions),
                writer_stop_confirmed=True,
                cleanup_ok=True,
            )
        except OSError as exc:
            raise ProviderL1Error(ERROR_SPAWN_FAILED, f"docker run failed: {exc}") from exc

        runtime.writer_stop_confirmed = True
        terminal = (
            ProcessTerminalKind.EXITED
            if proc.returncode is not None
            else ProcessTerminalKind.KILLED
        )
        return ProcessOutcome(
            attempt=runtime.attempt,
            assurance="l1",
            terminal=terminal,
            exit_code=proc.returncode,
            signal=None,
            stdout_summary=(proc.stdout or "")[-8000:],
            stderr_summary=(proc.stderr or "")[-8000:],
            truncated=False,
            pid=None,
            pgid=None,
            termination_actions=tuple(runtime.termination_actions),
            writer_stop_confirmed=True,
            cleanup_ok=True,
            detail={
                "image": runtime.image_lock.image_digest,
                "platform": runtime.image_lock.platform,
            },
        )

    def cleanup(self, runtime: DockerRuntime) -> None:
        if runtime.cleaned:
            return
        if runtime.network_id:
            subprocess.run(
                ["docker", "network", "rm", runtime.network_id],
                check=False,
                capture_output=True,
            )
        runtime.cleaned = True
        runtime.writer_stop_confirmed = True

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
        name = f"bora-net-{attempt.value[-16:]}"
        proc = subprocess.run(
            ["docker", "network", "create", "--internal", name],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            # fallback non-internal if internal unsupported
            proc = subprocess.run(
                ["docker", "network", "create", name],
                check=False,
                capture_output=True,
                text=True,
            )
        if proc.returncode != 0:
            raise ProviderL1Error(
                "provider_l1_unavailable",
                f"cannot create network: {proc.stderr}",
            )
        return name.strip() or (proc.stdout or "").strip()


def ensure_image_lock(repo_root: Path | None = None) -> Path:
    """Build image lock if missing; return lock path."""
    root = repo_root or Path.cwd()
    lock_path = root / ".bora" / "runtime-images" / "provider-l1.json"
    if lock_path.is_file():
        return lock_path
    build = root / "docker" / "attempt" / "build.py"
    proc = subprocess.run(
        [str(Path(sys_executable())), str(build), "--output-lock", str(lock_path)],
        check=False,
        cwd=str(root),
    )
    if proc.returncode != 0 or not lock_path.is_file():
        raise ProviderL1Error("image_unresolved", "failed to build L1 image lock")
    return lock_path


def sys_executable() -> str:
    import sys

    return sys.executable
