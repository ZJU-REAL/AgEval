"""Consume ``image_contribute`` multi-slot and bake plugin Ready into Attempt images.

Recognition (path install) ≠ Ready (this module). Spec 05 A1–A5.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import subprocess
from pathlib import Path
from typing import Any

from bora.adapters.provider_docker.types import DockerImageLock
from bora.config.model import LockedTaskConfig, thaw
from bora.plugins.bootstrap import ensure_bootstrapped
from bora.plugins.lifecycle import collect_image_contribute
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
    profiles = thaw(lock.agent_profiles) if lock.agent_profiles else []
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


def nooa_bound(lock: LockedTaskConfig) -> bool:
    profiles = thaw(lock.agent_profiles) if lock.agent_profiles else []
    if not isinstance(profiles, list):
        return False
    return any(isinstance(p, dict) and str(p.get("executor") or "") == "nooa" for p in profiles)


def needs_nooa_bake(declares: list[Any]) -> bool:
    for d in declares:
        if not isinstance(d, dict):
            continue
        if str(d.get("plugin") or "") == "nooa":
            return True
        bake = d.get("bake")
        if bake in {"nooa", "bora-executor-nooa"}:
            return True
        if isinstance(bake, list) and any(str(x) in {"nooa", "bora-executor-nooa"} for x in bake):
            return True
    return False


def _find_installed_plugin_root(plugin_id: str) -> Path | None:
    for entry in list_installed():
        if entry.plugin_id == plugin_id:
            root = resolve_package_root(entry)
            if root.is_dir():
                return root
    return None


def bake_nooa_layer(
    *,
    base_image: DockerImageLock,
    platform: str,
    out_tag: str,
    plugin_root: Path,
) -> DockerImageLock:
    """Second-stage docker build: FROM package image + nooa worker."""
    dockerfile = plugin_root / "docker" / "Dockerfile.bake"
    if not dockerfile.is_file():
        raise ImageContributeError(
            f"nooa bake Dockerfile missing: {dockerfile}",
            kind="plugin_not_ready",
        )
    worker = plugin_root / "worker" / "bora_executor_nooa.py"
    if not worker.is_file():
        raise ImageContributeError(
            f"nooa worker missing: {worker}",
            kind="plugin_not_ready",
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
            f"nooa image bake failed: {(proc.stderr or proc.stdout or '')[-2000:]}",
            kind="image_contribute_unsatisfied",
        )

    dig = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            out_tag,
            "--format",
            "{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if dig.returncode != 0:
        raise ImageContributeError("cannot inspect baked nooa image", kind="image_unresolved")
    image_digest = (dig.stdout or "").strip()
    build_input = hashlib.sha256(
        dockerfile.read_bytes() + worker.read_bytes() + base_image.image_digest.encode()
    ).hexdigest()
    return DockerImageLock(
        kind="docker-package-attempt-nooa",
        platform=platform,
        image_tag=out_tag,
        image_digest=image_digest,
        build_input_digest=f"sha256:{build_input}",
    )


def apply_image_contribute_bake(
    *,
    lock: LockedTaskConfig,
    base_image: DockerImageLock,
    platform: str,
) -> tuple[DockerImageLock, dict[str, Any]]:
    """Collect contribute declares and bake required layers (fail closed).

    Returns (possibly new image lock, evidence meta).
    """
    declares = collect_declares_for_lock(lock)
    meta: dict[str, Any] = {
        "declares": declares,
        "baked": [],
        "nooa_bound": nooa_bound(lock),
    }

    want_nooa = needs_nooa_bake(declares) or nooa_bound(lock)
    if not want_nooa:
        meta["status"] = "skipped_no_nooa"
        return base_image, meta

    if nooa_bound(lock) and not needs_nooa_bake(declares):
        # Bound but contribute chain empty → Recognition without Ready chain.
        raise ImageContributeError(
            "executor nooa bound but image_contribute chain empty or unsatisfied",
            kind="image_contribute_unsatisfied",
        )

    plugin_root = _find_installed_plugin_root("nooa")
    if plugin_root is None:
        raise ImageContributeError(
            "nooa not installed (Recognition required before Ready bake)",
            kind="plugin_not_ready",
        )

    short = hashlib.sha256(base_image.image_digest.encode()).hexdigest()[:12]
    out_tag = f"{base_image.image_tag}-nooa-{short}"
    baked = bake_nooa_layer(
        base_image=base_image,
        platform=platform,
        out_tag=out_tag,
        plugin_root=plugin_root,
    )
    meta["baked"] = ["nooa", "bora-executor-nooa"]
    meta["status"] = "baked"
    meta["image_tag"] = baked.image_tag
    meta["plugin_root"] = str(plugin_root)
    return baked, meta


def collect_image_contribute_sync(lock: LockedTaskConfig) -> list[Any]:
    """Test/helper alias for collect without bake."""
    return collect_declares_for_lock(lock)
