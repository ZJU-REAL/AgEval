"""L1 placement helpers (no private vendor CLI scrape).

Production coding-agent path: parent ACP client + ``docker exec -i`` attach
built by the ACP contrib via :func:`wrap_docker_exec`. Opaque target ids live
here for the Provider ledger.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from bora.provider.targets import ActorPhysicalBinding


def new_opaque_target_id() -> str:
    return f"tgt_{uuid.uuid4().hex[:16]}"


def effective_run_gid(actor: ActorPhysicalBinding) -> int:
    """Primary GID for docker exec: shared GID when shared_write is granted."""
    if actor.shared_gid is not None and actor.shared_write:
        return int(actor.shared_gid)
    return int(actor.gid)


def wrap_docker_exec(
    *,
    container_id: str,
    uid: int,
    gid: int,
    workdir: str,
    env: Mapping[str, str],
    argv: Sequence[str],
    shared_write: bool = False,
    shared_gid: int | None = None,
) -> list[str]:
    """Core-owned ``docker exec -u/-w`` prefix. Plugins supply argv + env only."""
    cmd: list[str] = [
        "docker",
        "exec",
        "-i",
        "-u",
        f"{int(uid)}:{int(gid)}",
        "-w",
        workdir,
    ]
    for key, val in env.items():
        if str(key).upper() in {"DOCKER_HOST", "DOCKER_SOCK"}:
            continue
        cmd.extend(["-e", f"{key}={val}"])
    cmd.append(container_id)
    argv_list = [str(a) for a in argv]
    if shared_gid is not None and shared_write:
        cmd.extend(["sh", "-c", 'umask 002; exec "$@"', "bora-actor", *argv_list])
    else:
        cmd.extend(argv_list)
    return cmd
