"""Consume ``image_contribute`` and bake installed-plugin Ready layers.

Recognition (path install) ≠ Ready (this module). Core does not interpret
plugin-named bake tokens. Each installed plugin that declares contribute and
ships ``docker/Dockerfile.bake`` is built as ``FROM ${BASE_IMAGE}`` with
context = plugin root. Bound *external* executors fail closed if the chain
is empty or the bake file is missing.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import subprocess
from pathlib import Path
from typing import Any

from bora.adapters.provider_docker.images import (
    hash_copy_sources,
    inspect_image_digest,
    is_official_base_noop_dockerfile,
    parse_dockerfile_copy_sources,
)
from bora.adapters.provider_docker.types import DockerImageLock
from bora.config.model import LockedTaskConfig, thaw
from bora.plugins.bootstrap import ensure_bootstrapped
from bora.plugins.lifecycle import collect_image_contribute
from bora.plugins.manifest import is_official_acp, is_official_plugin
from bora.plugins.protocol import intent_from_profile
from bora.plugins.resolve import resolve
from bora.plugins.store import list_installed, resolve_package_root


class ImageContributeError(Exception):
    """Bake / contribute failure (fail closed)."""

    def __init__(self, message: str, *, kind: str = "image_contribute_unsatisfied") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _await(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def graphs_for_lock(lock: LockedTaskConfig) -> list[Any]:
    """Resolve materialized graphs for every agent profile (for multi-slot chains)."""
    reg = ensure_bootstrapped()
    profiles = (
        thaw(getattr(lock, "agent_profiles", None)) if getattr(lock, "agent_profiles", None) else []
    )
    graphs: list[Any] = []
    if not isinstance(profiles, list) or not profiles:
        return graphs
    for p in profiles:
        if not isinstance(p, dict):
            continue
        intent = intent_from_profile(p)
        if not intent.profile_id:
            intent.profile_id = str(p.get("id") or "default")
        graphs.append(resolve(intent, reg, materialize=True))
    return graphs


def collect_declares_for_lock(lock: LockedTaskConfig) -> list[Any]:
    """Unique production entry: merge ``image_contribute`` across bound profile graphs."""
    merged: list[Any] = []
    seen: set[str] = set()
    for graph in graphs_for_lock(lock):
        declares = _await(collect_image_contribute(graph))
        for item in declares:
            key = repr(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def bound_executor_ids(lock: LockedTaskConfig) -> list[str]:
    profiles = (
        thaw(getattr(lock, "agent_profiles", None)) if getattr(lock, "agent_profiles", None) else []
    )
    if not isinstance(profiles, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for p in profiles:
        if not isinstance(p, dict):
            continue
        kind = str(p.get("executor") or "").strip()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        out.append(kind)
    return out


def _plugin_ids_from_declares(declares: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for d in declares:
        if not isinstance(d, dict):
            continue
        plugin = str(d.get("plugin") or "").strip()
        if not plugin or plugin in seen:
            continue
        seen.add(plugin)
        out.append(plugin)
    return out


def _find_installed_plugin_root(plugin_id: str) -> Path | None:
    for entry in list_installed():
        if entry.plugin_id == plugin_id:
            root = resolve_package_root(entry)
            if root.is_dir():
                return root
    return None


def bake_layer_content_digest(
    *,
    plugin_id: str,
    plugin_root: Path,
    dockerfile: Path,
    base_content_digest: str,
) -> str:
    """Hex digest of bake inputs — not ``docker image inspect`` id."""
    hasher = hashlib.sha256()
    hasher.update(b"plugin\0")
    hasher.update(plugin_id.encode("utf-8"))
    hasher.update(b"\0bake\0")
    hasher.update(dockerfile.read_bytes())
    hasher.update(b"\0base\0")
    hasher.update(base_content_digest.encode("utf-8"))
    hasher.update(b"\0copy\0")
    hash_copy_sources(
        plugin_root,
        parse_dockerfile_copy_sources(dockerfile.read_text(encoding="utf-8")),
        hasher,
    )
    return hasher.hexdigest()


def _base_content_digest(base_image: DockerImageLock) -> str:
    return base_image.build_input_digest or base_image.image_tag


def plugin_id_for_image_tag(plugin_id: str) -> str:
    """Docker tags cannot contain ``/``; Hub ``org/name`` becomes ``org--name``."""
    return plugin_id.replace("/", "--")


def baked_image_tag(base_image: DockerImageLock, plugin_id: str, bake_digest: str) -> str:
    return f"{base_image.image_tag}-{plugin_id_for_image_tag(plugin_id)}-{bake_digest[:12]}"


def should_reuse_official_attempt_image(lock: LockedTaskConfig, dockerfile_text: str) -> bool:
    """Official ACP + FROM-only package Dockerfile + no selected bake → reuse base."""
    bound = bound_executor_ids(lock)
    if not bound or any(not is_official_acp(kind) for kind in bound):
        return False
    declares = collect_declares_for_lock(lock)
    external = [p for p in _plugin_ids_from_declares(declares) if not is_official_plugin(p)]
    if external:
        return False
    return is_official_base_noop_dockerfile(dockerfile_text)


def bake_plugin_layer(
    *,
    base_image: DockerImageLock,
    platform: str,
    out_tag: str,
    plugin_id: str,
    plugin_root: Path,
) -> DockerImageLock:
    """Second-stage docker build: FROM package image + plugin Dockerfile.bake."""
    dockerfile = plugin_root / "docker" / "Dockerfile.bake"
    if not dockerfile.is_file():
        raise ImageContributeError(
            f"{plugin_id} bake Dockerfile missing: {dockerfile}",
            kind="plugin_not_ready",
        )
    bake_digest = bake_layer_content_digest(
        plugin_id=plugin_id,
        plugin_root=plugin_root,
        dockerfile=dockerfile,
        base_content_digest=_base_content_digest(base_image),
    )
    existing = inspect_image_digest(out_tag)
    if existing is not None:
        return DockerImageLock(
            kind="docker-package-attempt",
            platform=platform,
            image_tag=out_tag,
            image_digest=existing,
            build_input_digest=f"sha256:{bake_digest}",
        )

    cmd = [
        "docker",
        "buildx",
        "build",
        "--platform",
        platform,
        "-f",
        str(dockerfile),
        "--build-arg",
        f"BASE_IMAGE={base_image.image_tag}",
        "-t",
        out_tag,
        "--load",
        str(plugin_root.resolve()),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ImageContributeError(
            f"{plugin_id} image bake failed: {(proc.stderr or proc.stdout or '')[-2000:]}",
            kind="image_contribute_unsatisfied",
        )

    image_digest = inspect_image_digest(out_tag)
    if not image_digest:
        raise ImageContributeError(
            f"cannot inspect baked {plugin_id} image", kind="image_unresolved"
        )
    return DockerImageLock(
        kind="docker-package-attempt",
        platform=platform,
        image_tag=out_tag,
        image_digest=image_digest,
        build_input_digest=f"sha256:{bake_digest}",
    )


def apply_image_contribute_bake(
    *,
    lock: LockedTaskConfig,
    base_image: DockerImageLock,
    platform: str,
) -> tuple[DockerImageLock, dict[str, Any]]:
    """Collect contribute declares and bake required plugin layers (fail closed)."""
    declares = collect_declares_for_lock(lock)
    bound = bound_executor_ids(lock)
    external_bound = [k for k in bound if not is_official_plugin(k)]
    declared = _plugin_ids_from_declares(declares)
    meta: dict[str, Any] = {
        "declares": declares,
        "baked": [],
        "bound_executors": bound,
        "external_bound": external_bound,
    }

    for kind in external_bound:
        if kind not in declared:
            raise ImageContributeError(
                f"executor {kind!r} bound but image_contribute chain empty or unsatisfied",
                kind="image_contribute_unsatisfied",
            )

    plugins_to_bake = [p for p in declared if not is_official_plugin(p)]
    if not plugins_to_bake:
        meta["status"] = "skipped"
        return base_image, meta

    current = base_image
    baked_ids: list[str] = []
    for plugin_id in plugins_to_bake:
        plugin_root = _find_installed_plugin_root(plugin_id)
        if plugin_root is None:
            raise ImageContributeError(
                f"{plugin_id} not installed (Recognition required before Ready bake)",
                kind="plugin_not_ready",
            )
        dockerfile = plugin_root / "docker" / "Dockerfile.bake"
        if not dockerfile.is_file():
            raise ImageContributeError(
                f"{plugin_id} bound/declared but docker/Dockerfile.bake missing",
                kind="plugin_not_ready",
            )
        bake_digest = bake_layer_content_digest(
            plugin_id=plugin_id,
            plugin_root=plugin_root,
            dockerfile=dockerfile,
            base_content_digest=_base_content_digest(current),
        )
        out_tag = baked_image_tag(current, plugin_id, bake_digest)
        current = bake_plugin_layer(
            base_image=current,
            platform=platform,
            out_tag=out_tag,
            plugin_id=plugin_id,
            plugin_root=plugin_root,
        )
        baked_ids.append(plugin_id)

    meta["baked"] = baked_ids
    meta["status"] = "baked"
    meta["image_tag"] = current.image_tag
    return current, meta


def collect_image_contribute_sync(lock: LockedTaskConfig) -> list[Any]:
    """Test/helper alias for collect without bake."""
    return collect_declares_for_lock(lock)
