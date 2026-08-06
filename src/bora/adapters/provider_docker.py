"""DockerProvider — L1 isolated Attempt runtime (first implementation).

Uses Docker CLI (not Docker socket delegated into task containers).
Fails closed when daemon/image/platform unavailable.

Multi-actor support: long-lived ExecutionTargets with numeric UID/HOME and
``docker exec`` (never host CLI fallback on L1 agent path).
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from bora.provider.errors import ERROR_SPAWN_FAILED, ProviderError
from bora.provider.outcomes import ProcessOutcome, ProcessTerminalKind
from bora.provider.targets import (
    ActorPhysicalBinding,
    ExecutionTarget,
    IsolationMode,
    LogicalIsolationTopology,
    TargetLedger,
)
from bora.runtime.identity import AttemptIdentity


class ProviderL1Error(ProviderError):
    """L1-specific errors with stable kinds from Spec 07."""


# Base numeric UID for Attempt-private actors (non-root, non-host-identity claim).
_ACTOR_UID_BASE = 12000
_SHARED_GID_BASE = 13000


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
    writer_inventory: list[str] = field(default_factory=list)
    writer_stops: list[bool] = field(default_factory=list)
    # Multi-actor L1 private ledger (handles never exposed publicly).
    target_ledger: TargetLedger | None = None
    agent_container_ids: list[str] = field(default_factory=list)

    def register_writer(self, name: str) -> None:
        self.writer_inventory.append(name)

    def record_writer_stop(self, confirmed: bool) -> None:
        self.writer_stops.append(confirmed)
        self.writer_stop_confirmed = all(self.writer_stops) if self.writer_stops else False


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
                    _copy_package_filtered(runtime.package_host, filtered)
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

    def prepare_agent_targets(
        self,
        runtime: DockerRuntime,
        topology: LogicalIsolationTopology,
        *,
        cred_root: Path,
        network_mode: str | None = None,
    ) -> TargetLedger:
        """Materialize Attempt-private ExecutionTargets before Harness starts.

        On any create failure, stop already-created targets and raise.
        """
        if runtime.image_lock is None or runtime.workdir_host is None:
            raise ProviderL1Error("invalid_plan", "runtime not prepared")
        if runtime.cleaned:
            raise ProviderL1Error("already_cleaned", "runtime cleaned")

        ledger = TargetLedger(topology=topology)
        net = network_mode or topology.network
        created: list[str] = []

        try:
            if topology.mode == IsolationMode.SHARED_CONTAINER:
                # One container for all actors; shared host workspace is intentional.
                group_id = topology.groups[0].group_id if topology.groups else "default"
                target = self._start_long_lived_target(
                    runtime,
                    group_id=group_id,
                    network_mode=net,
                    cred_root=cred_root,
                    generation=1,
                    isolation_mode=IsolationMode.SHARED_CONTAINER,
                )
                created.append(target.container_id or "")
                ledger.targets[target.target_id] = target
                shared_gid = _SHARED_GID_BASE
                bindings: list[ActorPhysicalBinding] = []
                for idx, actor in enumerate(topology.actors):
                    uid = _ACTOR_UID_BASE + idx
                    has_shared = bool(actor.shared_write)
                    binding = ActorPhysicalBinding(
                        actor_id=actor.actor_id,
                        group_id=actor.group_id,
                        target_id=target.target_id,
                        uid=uid,
                        gid=uid,  # private primary group
                        home_container=f"/actor-homes/{actor.actor_id}",
                        shared_gid=shared_gid if has_shared else None,
                        shared_write=actor.shared_write,
                        generation=target.generation,
                    )
                    ledger.actors[actor.actor_id] = binding
                    bindings.append(binding)
                self._bootstrap_actor_fs(target, bindings, shared_gid=shared_gid)
            else:
                # container-per-group: one target per group; per-group workspace only
                # (no cross-container shared RW volumes — constitution §5).
                actor_index = 0
                for gidx, group in enumerate(topology.groups):
                    target = self._start_long_lived_target(
                        runtime,
                        group_id=group.group_id,
                        network_mode=net,
                        cred_root=cred_root,
                        generation=1,
                        isolation_mode=IsolationMode.CONTAINER_PER_GROUP,
                    )
                    created.append(target.container_id or "")
                    ledger.targets[target.target_id] = target
                    shared_gid = _SHARED_GID_BASE + gidx
                    group_bindings: list[ActorPhysicalBinding] = []
                    for aid in group.actor_ids:
                        actor = topology.actor(aid)
                        if actor is None:
                            raise ProviderL1Error(
                                "invalid_plan", f"missing actor in topology: {aid}"
                            )
                        uid = _ACTOR_UID_BASE + actor_index
                        actor_index += 1
                        has_shared = bool(actor.shared_write)
                        binding = ActorPhysicalBinding(
                            actor_id=aid,
                            group_id=group.group_id,
                            target_id=target.target_id,
                            uid=uid,
                            gid=uid,
                            home_container=f"/actor-homes/{aid}",
                            shared_gid=shared_gid if has_shared else None,
                            shared_write=actor.shared_write,
                            generation=target.generation,
                        )
                        ledger.actors[aid] = binding
                        group_bindings.append(binding)
                    self._bootstrap_actor_fs(target, group_bindings, shared_gid=shared_gid)

            runtime.target_ledger = ledger
            runtime.agent_container_ids = [c for c in created if c]
            for cid in runtime.agent_container_ids:
                runtime.register_writer(f"agent_target:{cid[:12]}")
            # Public mount inventory (no host paths / docker ids).
            runtime.policy_digests["agent_workspace_mode"] = (
                "shared" if topology.mode == IsolationMode.SHARED_CONTAINER else "per_group"
            )
            return ledger
        except Exception:
            # Partial prepare: reverse cleanup before Harness start.
            for cid in reversed(created):
                if cid:
                    subprocess.run(
                        ["docker", "rm", "-f", cid],
                        check=False,
                        capture_output=True,
                    )
            raise

    def stop_agent_targets(self, runtime: DockerRuntime) -> None:
        """Stop all agent targets; mark writer stop facts."""
        if runtime.target_ledger is None:
            return
        for target in runtime.target_ledger.targets.values():
            cid = target.container_id
            if not cid:
                target.state = "dead"
                runtime.record_writer_stop(True)
                self._rm_target_volumes(target)
                continue
            kill = subprocess.run(
                ["docker", "rm", "-f", cid],
                check=False,
                capture_output=True,
            )
            gone = (
                subprocess.run(
                    ["docker", "inspect", cid],
                    check=False,
                    capture_output=True,
                ).returncode
                != 0
            )
            confirmed = gone or kill.returncode == 0
            runtime.record_writer_stop(confirmed)
            target.state = "cleaned" if confirmed else "dead"
            target.container_id = None
            self._rm_target_volumes(target)
        runtime.agent_container_ids.clear()

    @staticmethod
    def _rm_target_volumes(target: ExecutionTarget) -> None:
        raw = target.workspace_volume
        if not raw:
            return
        for name in raw.split(","):
            name = name.strip()
            if name:
                subprocess.run(
                    ["docker", "volume", "rm", "-f", name],
                    check=False,
                    capture_output=True,
                )
        target.workspace_volume = None

    def mark_target_dead(self, runtime: DockerRuntime, target_id: str) -> None:
        """Fence a target after unexpected death (generation stays; state=dead)."""
        if runtime.target_ledger is None:
            return
        t = runtime.target_ledger.targets.get(target_id)
        if t is None:
            return
        if t.container_id:
            subprocess.run(
                ["docker", "rm", "-f", t.container_id],
                check=False,
                capture_output=True,
            )
        t.state = "dead"
        t.container_id = None

    def _start_long_lived_target(
        self,
        runtime: DockerRuntime,
        *,
        group_id: str,
        network_mode: str,
        cred_root: Path,
        generation: int,
        isolation_mode: IsolationMode,
    ) -> ExecutionTarget:
        assert runtime.image_lock is not None
        assert runtime.workdir_host is not None
        from bora.adapters.agent_container import new_opaque_target_id

        target_id = new_opaque_target_id()
        name = f"bora-agt-{runtime.attempt.value[-10:]}-{uuid.uuid4().hex[:6]}"
        package_mount = runtime.package_host
        if runtime.policy_digests.get("hide_evaluation") == "True" and runtime.package_host:
            filtered = runtime.workdir_host / "package_view"
            if not filtered.exists():
                _copy_package_filtered(runtime.package_host, filtered)
            package_mount = filtered

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--security-opt",
            "no-new-privileges",
            # Start as root only to bootstrap homes; exec uses numeric actor UIDs.
            "--user",
            "0:0",
        ]
        if network_mode == "bridge":
            cmd.extend(["--network", "bridge"])
        elif network_mode == "none":
            cmd.extend(["--network", "none"])
        elif runtime.network_id:
            cmd.extend(["--network", runtime.network_id])
        else:
            cmd.extend(["--network", "none"])

        if package_mount is not None:
            cmd.extend(["-v", f"{package_mount}:/attempt/package:ro"])

        # Workspace mount policy:
        # - Always prefer host bind under workdir so seed + host harness + agent
        #   share one tree (terminal cwd writes visible to harness publish).
        # - Multi-actor shared_write ACL still applied in-container via chown/chmod
        #   on that bind (Linux VM enforces; Docker Desktop may be looser).
        # - container-per-group: per-group host dir — no cross-group RW volume.
        workspace_volume: str | None = None
        if isolation_mode == IsolationMode.CONTAINER_PER_GROUP:
            group_ws = runtime.workdir_host / "group_ws" / group_id
            group_ws.mkdir(parents=True, exist_ok=True)
            cmd.extend(["-v", f"{group_ws}:/attempt/workspace:rw"])
        else:
            # shared-container: same Attempt workspace the host harness reads.
            host_ws = runtime.workdir_host / "workspace"
            host_ws.mkdir(parents=True, exist_ok=True)
            cmd.extend(["-v", f"{host_ws}:/attempt/workspace:rw"])

        cmd.extend(["-v", f"{cred_root}:/creds:ro"])
        # Actor private homes: named volume for real 0700 isolation.
        home_vol = f"bora-home-{runtime.attempt.value[-12:]}-{group_id[:8]}-{uuid.uuid4().hex[:6]}"
        hv = subprocess.run(
            ["docker", "volume", "create", home_vol],
            check=False,
            capture_output=True,
            text=True,
        )
        if hv.returncode != 0:
            if workspace_volume:
                subprocess.run(
                    ["docker", "volume", "rm", "-f", workspace_volume],
                    check=False,
                    capture_output=True,
                )
            raise ProviderL1Error(
                ERROR_SPAWN_FAILED,
                f"home volume create failed: {(hv.stderr or '')[-500:]}",
            )
        cmd.extend(["-v", f"{home_vol}:/actor-homes:rw"])

        # Long-lived sleeper; never mount docker.sock.
        cmd.extend(
            [
                "--workdir",
                "/attempt/workspace",
                runtime.image_lock.image_tag,
                "sleep",
                "infinity",
            ]
        )
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            subprocess.run(
                ["docker", "volume", "rm", "-f", home_vol],
                check=False,
                capture_output=True,
            )
            if workspace_volume:
                subprocess.run(
                    ["docker", "volume", "rm", "-f", workspace_volume],
                    check=False,
                    capture_output=True,
                )
            raise ProviderL1Error(
                ERROR_SPAWN_FAILED,
                f"agent target start failed: {(proc.stderr or proc.stdout or '')[-1500:]}",
            )
        cid = (proc.stdout or "").strip()
        if not cid:
            raise ProviderL1Error(ERROR_SPAWN_FAILED, "agent target missing container id")
        # Stash home volume name on container_name side-channel via labels? Keep
        # both volume names in workspace_volume field joined for cleanup.
        vol_ledger = home_vol if not workspace_volume else f"{workspace_volume},{home_vol}"
        return ExecutionTarget(
            target_id=target_id,
            group_id=group_id,
            generation=generation,
            container_id=cid,
            container_name=name,
            workspace_volume=vol_ledger,
            state="ready",
            image_digest=runtime.image_lock.image_digest,
            image_tag=runtime.image_lock.image_tag,
        )

    def _bootstrap_actor_fs(
        self,
        target: ExecutionTarget,
        bindings: list[ActorPhysicalBinding],
        *,
        shared_gid: int,
    ) -> None:
        """Create private HOME 0700 and shared_write dirs with real GID grants.

        Single actor: workspace root owned by that actor (cwd writes for terminal tasks).
        Multi-actor: workspace root root-owned 0755; only explicit shared_write paths
        are 2770 root:shared_gid (actors need supplementary shared_gid to write).
        """
        if not target.container_id:
            raise ProviderL1Error(ERROR_SPAWN_FAILED, "bootstrap without container")
        # Collect union of shared_write paths for this target.
        shared_paths: set[str] = set()
        for b in bindings:
            shared_paths.update(b.shared_write)

        lines = [
            "set -e",
            "mkdir -p /actor-homes /attempt/workspace",
            # Ensure shared GID exists (numeric group only is enough for chown).
            f"groupadd -g {shared_gid} bora-shared-{shared_gid} 2>/dev/null || true",
        ]
        # Single-actor Attempt: actor owns workspace root (terminal-class cwd writes).
        # Multi-actor: root owns root dir 0755; only explicit shared_write is group-writable.
        if len(bindings) == 1:
            only = bindings[0]
            lines.append(f"chown -R {only.uid}:{only.gid} /attempt/workspace")
            lines.append("chmod 0755 /attempt/workspace")
        else:
            lines.append("chown root:root /attempt/workspace")
            lines.append("chmod 0755 /attempt/workspace")
        for rel in sorted(shared_paths):
            sp = f"/attempt/workspace/{rel}"
            lines.append(f"mkdir -p '{sp}'")
            lines.append(f"chown root:{shared_gid} '{sp}'")
            lines.append(f"chmod 2770 '{sp}'")

        for b in bindings:
            home = b.home_container
            lines.append(f"mkdir -p '{home}'")
            lines.append(f"chmod 0700 '{home}'")
            lines.append(f"chown {b.uid}:{b.gid} '{home}'")
            # Projected credential copies (allowlist) into actor HOME.
            lines.append(f"mkdir -p '{home}/.codex'")
            lines.append(
                f"if [ -f /creds/codex_home/auth.json ]; then "
                f"cp /creds/codex_home/auth.json '{home}/.codex/auth.json'; fi"
            )
            lines.append(
                f"if [ -f /creds/codex_home/config.toml ]; then "
                f"cp /creds/codex_home/config.toml '{home}/.codex/config.toml'; fi"
            )
            lines.append(f"chown -R {b.uid}:{b.gid} '{home}/.codex'")
            lines.append(f"chmod 0700 '{home}/.codex'")
            # Create private primary group if needed (numeric chown works without).
            lines.append(f"groupadd -g {b.gid} actor-g-{b.gid} 2>/dev/null || true")
            lines.append(
                f"useradd -u {b.uid} -g {b.gid} -d '{home}' -M actor-{b.uid} 2>/dev/null || true"
            )
            if b.shared_gid is not None:
                lines.append(f"usermod -aG {b.shared_gid} actor-{b.uid} 2>/dev/null || true")

        script = "\n".join(lines)
        proc = subprocess.run(
            ["docker", "exec", "-u", "0:0", target.container_id, "sh", "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise ProviderL1Error(
                ERROR_SPAWN_FAILED,
                f"actor fs bootstrap failed: {(proc.stderr or proc.stdout or '')[-1000:]}",
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
    """Build official base image lock if missing; return lock path."""
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


def ensure_base_image(repo_root: Path | None = None) -> DockerImageLock:
    """Ensure official ``bora-attempt:l1`` exists and return its lock record."""
    path = ensure_image_lock(repo_root)
    return DockerImageLock.load(path)


def build_package_image(
    *,
    package_root: Path,
    dockerfile_rel: str = "environment/Dockerfile",
    platform: str = "linux/arm64",
    tag: str,
    repo_root: Path | None = None,
) -> DockerImageLock:
    """Build Attempt image from package Dockerfile (context = package root).

    Ensures official base is available first so ``FROM bora-attempt:l1`` resolves.
    """
    package_root = package_root.resolve()
    df = (package_root / dockerfile_rel).resolve()
    try:
        df.relative_to(package_root)
    except ValueError as exc:
        raise ProviderL1Error(
            "path_outside_package",
            f"dockerfile outside package: {dockerfile_rel}",
        ) from exc
    if not df.is_file():
        raise ProviderL1Error(
            "image_unresolved",
            f"missing package Dockerfile: {dockerfile_rel}",
        )

    ensure_base_image(repo_root)

    cmd = [
        "docker",
        "buildx",
        "build",
        "--platform",
        platform,
        "-f",
        str(df),
        "-t",
        tag,
        "--load",
        str(package_root),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ProviderL1Error(
            "image_unresolved",
            f"package image build failed: {(proc.stderr or proc.stdout or '')[-2000:]}",
        )

    dig = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            tag,
            "--format",
            "{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if dig.returncode != 0:
        raise ProviderL1Error("image_unresolved", "cannot inspect package image")
    image_digest = (dig.stdout or "").strip()
    build_input = __import__("hashlib").sha256(df.read_bytes()).hexdigest()
    return DockerImageLock(
        kind="docker-package-attempt",
        platform=platform,
        image_tag=tag,
        image_digest=image_digest,
        build_input_digest=f"sha256:{build_input}",
    )


def sys_executable() -> str:
    import sys

    return sys.executable
