"""Multi-actor L1 ExecutionTarget lifecycle (long-lived containers + actor FS)."""

from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path

from bora.adapters.provider_docker.cli_supervise import supervise_docker_cli
from bora.adapters.provider_docker.errors import ProviderL1Error
from bora.adapters.provider_docker.package_view import copy_package_filtered
from bora.adapters.provider_docker.types import (
    _ACTOR_UID_BASE,
    _SHARED_GID_BASE,
    DockerRuntime,
)
from bora.provider.errors import ERROR_SPAWN_FAILED
from bora.provider.outcomes import ProcessTerminalKind
from bora.provider.targets import (
    ActorPhysicalBinding,
    ExecutionTarget,
    IsolationMode,
    LogicalIsolationTopology,
    TargetLedger,
)
from bora.runtime.identity import AttemptIdentity

# Actor FS bootstrap is short host→container setup; never hang forever.
_ACTOR_FS_BOOTSTRAP_TIMEOUT_SECONDS = 120.0
# Wait until image ENTRYPOINT has exec'd the sleeper (seed finished).
_ENTRYPOINT_IDLE_TIMEOUT_SECONDS = 180.0


def wait_entrypoint_idle(
    container_id: str, *, timeout_seconds: float = _ENTRYPOINT_IDLE_TIMEOUT_SECONDS
) -> None:
    """Block until PID 1 is ``sleep`` (entrypoint finished) or the container died."""
    deadline = time.monotonic() + timeout_seconds
    last = ""
    while time.monotonic() < deadline:
        state = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}} {{.State.Status}}",
                container_id,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        running = (state.stdout or "").strip()
        last = running
        if not running.startswith("true"):
            raise ProviderL1Error(
                ERROR_SPAWN_FAILED,
                f"agent target exited before entrypoint idle: {running}",
            )
        comm = subprocess.run(
            ["docker", "exec", container_id, "cat", "/proc/1/comm"],
            check=False,
            capture_output=True,
            text=True,
        )
        if comm.returncode == 0 and (comm.stdout or "").strip() == "sleep":
            return
        time.sleep(0.2)
    raise ProviderL1Error(
        ERROR_SPAWN_FAILED,
        f"entrypoint did not reach idle within {timeout_seconds:g}s ({last})",
    )


class DockerMultiActorMixin:
    """Mixin: prepare / stop / bootstrap Attempt-private agent targets."""

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
        created: list[ExecutionTarget] = []

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
                created.append(target)
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
                self._bootstrap_actor_fs(
                    target, bindings, shared_gid=shared_gid, attempt=runtime.attempt
                )
            else:
                # container-per-group: one target per group; per-group workspace only
                # (no cross-container shared RW volumes — design/05 L1 isolation).
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
                    created.append(target)
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
                    self._bootstrap_actor_fs(
                        target,
                        group_bindings,
                        shared_gid=shared_gid,
                        attempt=runtime.attempt,
                    )

            runtime.target_ledger = ledger
            runtime.agent_container_ids = [t.container_id for t in created if t.container_id]
            for cid in runtime.agent_container_ids:
                runtime.register_writer(f"agent_target:{cid[:12]}")
            # Public mount inventory (no host paths / docker ids).
            runtime.policy_digests["agent_workspace_mode"] = (
                "shared" if topology.mode == IsolationMode.SHARED_CONTAINER else "per_group"
            )
            return ledger
        except Exception:
            # Partial prepare: drop containers and Attempt-owned volumes.
            for target in reversed(created):
                self._rm_target(target)
            raise

    def fence_agent_writers(self, runtime: DockerRuntime) -> None:
        """Confirm agent writers stopped; keep containers for same-Attempt eval.

        Does not ``docker rm``, reconnect, or rewrite the live network.
        """
        if runtime.target_ledger is None:
            return
        for target in runtime.target_ledger.targets.values():
            cid = target.container_id
            if not cid:
                target.state = "dead"
                runtime.record_writer_stop(True)
                continue
            inspect = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", cid],
                check=False,
                capture_output=True,
                text=True,
            )
            running = inspect.returncode == 0 and inspect.stdout.strip().lower() == "true"
            if not running:
                target.state = "dead"
                runtime.record_writer_stop(False)
                continue
            runtime.record_writer_stop(True)

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
                ["docker", "rm", "-fv", cid],
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

    @classmethod
    def _rm_target(cls, target: ExecutionTarget) -> None:
        cid = target.container_id
        if cid:
            subprocess.run(
                ["docker", "rm", "-fv", cid],
                check=False,
                capture_output=True,
            )
            target.container_id = None
        cls._rm_target_volumes(target)
        if target.state != "cleaned":
            target.state = "dead"

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
        self._rm_target(t)
        t.state = "dead"

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
                copy_package_filtered(runtime.package_host, filtered)
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
        try:
            wait_entrypoint_idle(cid)
        except ProviderL1Error:
            subprocess.run(["docker", "rm", "-fv", cid], check=False, capture_output=True)
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
            raise
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
        attempt: AttemptIdentity,
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
            # Plugin extras first; allowlisted auth copies win on overlap.
            lines.append(
                f"if [ -d /creds/home_overlay ]; then cp -a /creds/home_overlay/. '{home}/'; fi"
            )
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
            # Pi agent auth (optional)
            lines.append(f"mkdir -p '{home}/.pi/agent'")
            lines.append(
                f"if [ -f /creds/pi_home/agent/auth.json ]; then "
                f"cp /creds/pi_home/agent/auth.json '{home}/.pi/agent/auth.json'; "
                f"chmod 0600 '{home}/.pi/agent/auth.json'; fi"
            )
            lines.append(f"chown -R {b.uid}:{b.gid} '{home}/.pi' 2>/dev/null || true")
            # OpenCode auth (optional) under XDG_DATA_HOME default
            lines.append(f"mkdir -p '{home}/.local/share/opencode'")
            lines.append(
                f"if [ -f /creds/opencode/auth.json ]; then "
                f"cp /creds/opencode/auth.json '{home}/.local/share/opencode/auth.json'; "
                f"chmod 0600 '{home}/.local/share/opencode/auth.json'; fi"
            )
            lines.append(f"chown -R {b.uid}:{b.gid} '{home}/.local' 2>/dev/null || true")
            # Grok Build ACP host login (optional) — $HOME/.grok/auth.json
            lines.append(f"mkdir -p '{home}/.grok'")
            lines.append(
                f"if [ -f /creds/grok_home/auth.json ]; then "
                f"cp /creds/grok_home/auth.json '{home}/.grok/auth.json'; "
                f"chmod 0600 '{home}/.grok/auth.json'; fi"
            )
            lines.append(f"chown -R {b.uid}:{b.gid} '{home}/.grok' 2>/dev/null || true")
            lines.append(f"chmod 0700 '{home}/.grok' 2>/dev/null || true")
            # Overlay + auth copies land as root; actor must own the whole HOME.
            lines.append(f"chown -R {b.uid}:{b.gid} '{home}'")
            # Create private primary group if needed (numeric chown works without).
            lines.append(f"groupadd -g {b.gid} actor-g-{b.gid} 2>/dev/null || true")
            lines.append(
                f"useradd -u {b.uid} -g {b.gid} -d '{home}' -M actor-{b.uid} 2>/dev/null || true"
            )
            if b.shared_gid is not None:
                lines.append(f"usermod -aG {b.shared_gid} actor-{b.uid} 2>/dev/null || true")

        script = "\n".join(lines)
        try:
            outcome = supervise_docker_cli(
                ["docker", "exec", "-u", "0:0", target.container_id, "sh", "-c", script],
                timeout_seconds=_ACTOR_FS_BOOTSTRAP_TIMEOUT_SECONDS,
                attempt=attempt,
            )
        except FileNotFoundError as exc:
            raise ProviderL1Error(
                ERROR_SPAWN_FAILED,
                f"actor fs bootstrap failed: {exc}",
            ) from exc
        if outcome.terminal == ProcessTerminalKind.TIMED_OUT:
            raise ProviderL1Error(
                ERROR_SPAWN_FAILED,
                "actor fs bootstrap timed out",
            )
        if outcome.terminal == ProcessTerminalKind.SPAWN_FAILED or outcome.exit_code != 0:
            detail = (outcome.stderr_summary or outcome.stdout_summary or "")[-1000:]
            raise ProviderL1Error(
                ERROR_SPAWN_FAILED,
                f"actor fs bootstrap failed: {detail}",
            )
