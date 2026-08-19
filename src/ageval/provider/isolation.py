"""Parse and validate logical agent_isolation topology from locked provider config."""

from __future__ import annotations

from typing import Any

from ageval.config.errors import (
    ERROR_INVALID_SCHEMA,
    ERROR_UNKNOWN_PROFILE,
    ERROR_UNSUPPORTED_CAPABILITY,
    ConfigError,
)
from ageval.provider.targets import (
    IsolationMode,
    LogicalActor,
    LogicalGroup,
    LogicalIsolationTopology,
)


def parse_logical_topology(
    provider: dict[str, Any],
    *,
    profile_ids: set[str],
    implicit_profiles: list[str] | None = None,
) -> LogicalIsolationTopology | None:
    """Return topology when ``agent_isolation`` present, or None.

    When *implicit_profiles* is provided and agent_isolation is absent, build a
    single-actor implicit topology for Phase 0 SDK L1 parity.
    """
    raw = provider.get("agent_isolation")
    network = str(provider.get("network") or "bridge")
    if network not in {"bridge", "none"}:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "provider.network must be bridge|none for L1 agent targets",
            location="/provider/network",
        )

    if raw is None:
        if not implicit_profiles:
            return None
        # Implicit single actor for docker SDK path without explicit isolation.
        actor_id = "default"
        profiles = tuple(implicit_profiles)
        return LogicalIsolationTopology(
            mode=IsolationMode.SHARED_CONTAINER,
            groups=(LogicalGroup(group_id="default", actor_ids=(actor_id,), shared_write=()),),
            actors=(
                LogicalActor(
                    actor_id=actor_id,
                    group_id="default",
                    profiles=profiles,
                    shared_write=(),
                ),
            ),
            network=network,
        )

    if not isinstance(raw, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "provider.agent_isolation must be a mapping",
            location="/provider/agent_isolation",
        )

    mode_raw = raw.get("mode")
    allowed_modes = {
        IsolationMode.SHARED_CONTAINER.value,
        IsolationMode.CONTAINER_PER_GROUP.value,
    }
    if mode_raw not in allowed_modes:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "agent_isolation.mode must be shared-container|container-per-group",
            location="/provider/agent_isolation/mode",
        )
    mode = IsolationMode(str(mode_raw))

    groups_raw = raw.get("groups")
    if not isinstance(groups_raw, list) or not groups_raw:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "agent_isolation.groups must be a non-empty list",
            location="/provider/agent_isolation/groups",
        )

    groups: list[LogicalGroup] = []
    actors: list[LogicalActor] = []
    seen_group: set[str] = set()
    seen_actor: set[str] = set()

    for gidx, g in enumerate(groups_raw):
        gloc = f"/provider/agent_isolation/groups/{gidx}"
        if not isinstance(g, dict):
            raise ConfigError(ERROR_INVALID_SCHEMA, "group must be a mapping", location=gloc)
        gid = g.get("id")
        if not isinstance(gid, str) or not gid.strip():
            raise ConfigError(ERROR_INVALID_SCHEMA, "group.id required", location=f"{gloc}/id")
        gid = gid.strip()
        if gid in seen_group:
            raise ConfigError(
                ERROR_INVALID_SCHEMA, f"duplicate group id: {gid}", location=f"{gloc}/id"
            )
        seen_group.add(gid)

        shared_write = _validate_shared_write(g.get("shared_write") or [], f"{gloc}/shared_write")
        actors_raw = g.get("actors")
        if not isinstance(actors_raw, list) or not actors_raw:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "group.actors must be a non-empty list",
                location=f"{gloc}/actors",
            )

        actor_ids: list[str] = []
        for aidx, a in enumerate(actors_raw):
            aloc = f"{gloc}/actors/{aidx}"
            if not isinstance(a, dict):
                raise ConfigError(ERROR_INVALID_SCHEMA, "actor must be a mapping", location=aloc)
            aid = a.get("id")
            if not isinstance(aid, str) or not aid.strip():
                raise ConfigError(ERROR_INVALID_SCHEMA, "actor.id required", location=f"{aloc}/id")
            aid = aid.strip()
            if aid in seen_actor:
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    f"duplicate actor id: {aid}",
                    location=f"{aloc}/id",
                )
            seen_actor.add(aid)
            actor_ids.append(aid)

            profiles = a.get("profiles")
            if not isinstance(profiles, list) or not profiles:
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "actor.profiles must be a non-empty list",
                    location=f"{aloc}/profiles",
                )
            prof_ids: list[str] = []
            for p in profiles:
                if not isinstance(p, str) or not p:
                    raise ConfigError(
                        ERROR_INVALID_SCHEMA,
                        "actor.profiles entries must be non-empty strings",
                        location=f"{aloc}/profiles",
                    )
                if p not in profile_ids:
                    raise ConfigError(
                        ERROR_UNKNOWN_PROFILE,
                        f"unknown profile in actor allowlist: {p}",
                        location=f"{aloc}/profiles",
                    )
                prof_ids.append(p)

            actors.append(
                LogicalActor(
                    actor_id=aid,
                    group_id=gid,
                    profiles=tuple(prof_ids),
                    shared_write=shared_write,
                )
            )

        groups.append(
            LogicalGroup(group_id=gid, actor_ids=tuple(actor_ids), shared_write=shared_write)
        )

    return LogicalIsolationTopology(
        mode=mode,
        groups=tuple(groups),
        actors=tuple(actors),
        network=network,
    )


def validate_agent_isolation_in_provider(
    provider: dict[str, Any],
    *,
    profile_ids: set[str],
) -> None:
    """Fail-closed schema validation during load_and_lock.

    Rejects physical/runtime fields that must never appear in YAML/lock.
    """
    raw = provider.get("agent_isolation")
    if raw is None:
        return
    if provider.get("kind") != "docker":
        raise ConfigError(
            ERROR_UNSUPPORTED_CAPABILITY,
            "agent_isolation requires provider.kind: docker",
            location="/provider/agent_isolation",
        )
    # Forbidden physical fields anywhere under agent_isolation.
    forbidden = {
        "container_id",
        "container_ids",
        "docker_id",
        "uid",
        "gid",
        "uids",
        "gids",
        "socket",
        "socket_path",
        "docker_sock",
        "network_id",
        "network_name",
        "credential",
        "credentials",
        "home",
        "target_id",
    }
    _reject_forbidden_keys(raw, "/provider/agent_isolation", forbidden)
    # Full parse validates structure + profile refs.
    parse_logical_topology(provider, profile_ids=profile_ids)


def _validate_shared_write(paths: Any, location: str) -> tuple[str, ...]:
    if not isinstance(paths, list):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "shared_write must be a list of relative paths",
            location=location,
        )
    out: list[str] = []
    for p in paths:
        if not isinstance(p, str) or not p.strip():
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "shared_write entries must be non-empty strings",
                location=location,
            )
        rel = p.strip().replace("\\", "/")
        if rel.startswith("/") or rel.startswith("~"):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "shared_write paths must be workspace-relative (no absolute)",
                location=location,
            )
        parts = [x for x in rel.split("/") if x and x != "."]
        if ".." in parts:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "shared_write paths must not contain ..",
                location=location,
            )
        if not parts:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "shared_write path is empty after normalize",
                location=location,
            )
        out.append("/".join(parts))
    return tuple(out)


def _reject_forbidden_keys(node: Any, location: str, forbidden: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            key = str(k)
            if key.lower() in forbidden or key in forbidden:
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    f"physical/runtime field forbidden in lock: {key}",
                    location=f"{location}/{key}",
                )
            _reject_forbidden_keys(v, f"{location}/{key}", forbidden)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _reject_forbidden_keys(item, f"{location}/{i}", forbidden)
