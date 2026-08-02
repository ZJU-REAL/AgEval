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
    assurance: str = "l0"  # default honest; only upgrade after full L1 workload
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
        # Network: default none unless allowed. No silent policy downgrade.
        if not network or runtime.network_id is None:
            cmd.extend(["--network", "none"])
        else:
            cmd.extend(["--network", runtime.network_id])

        # Package mount: when hide_evaluation is set, mount a filtered tree without
        # evaluation/ and gold-like paths (physical hide for container probes).
        package_mount = runtime.package_host
        if (
            runtime.policy_digests.get("hide_evaluation") == "True"
            and runtime.workdir_host is not None
            and runtime.package_host is not None
        ):
            filtered = runtime.workdir_host / "package_view"
            if not filtered.exists():
                _copy_package_filtered(runtime.package_host, filtered)
            package_mount = filtered
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
            runtime.writer_stop_confirmed = gone and kill.returncode == 0
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

        # docker run --rm waits for main process exit; that is one writer, not a tree.
        runtime.writer_stop_confirmed = proc.returncode is not None
        terminal = (
            ProcessTerminalKind.EXITED
            if proc.returncode is not None
            else ProcessTerminalKind.KILLED
        )
        return ProcessOutcome(
            attempt=runtime.attempt,
            # Probe/container helper grade: do not claim full Attempt L1 isolation here.
            assurance="l0",
            terminal=terminal,
            exit_code=proc.returncode,
            signal=None,
            stdout_summary=(proc.stdout or "")[-8000:],
            stderr_summary=(proc.stderr or "")[-8000:],
            truncated=False,
            pid=None,
            pgid=None,
            termination_actions=tuple(runtime.termination_actions),
            writer_stop_confirmed=runtime.writer_stop_confirmed,
            cleanup_ok=True,
            detail={
                "image": runtime.image_lock.image_digest,
                "platform": runtime.image_lock.platform,
                "containment": "single_container_probe",
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


def _copy_package_filtered(src: Path, dest: Path) -> None:
    """Copy package tree excluding evaluation/ and common gold locations."""
    import shutil

    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        name = item.name
        if name in {"evaluation", ".bora", "__pycache__"}:
            continue
        target = dest / name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


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
