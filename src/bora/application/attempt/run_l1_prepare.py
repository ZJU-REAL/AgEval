"""L1 Attempt prepare helpers — image build, runtime, credential env projection."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from bora.adapters.provider_docker import (
    DockerProvider,
    DockerRuntime,
    build_package_image,
    ensure_base_image,
    ensure_image_lock,
)
from bora.runtime.identity import AttemptIdentity


def prepare_l1_runtime(
    package_root: Path,
    lock: Any,
    run_dir: Path,
    *,
    attempt: AttemptIdentity,
    network_mode: str = "none",
) -> tuple[DockerProvider, DockerRuntime, dict[str, Any]]:
    from bora.application.attempt.extension_hooks import hook_prepare
    from bora.application.plugin_ops.image_contribute_bake import (
        ImageContributeError,
        apply_image_contribute_bake,
    )
    from bora.config.model import thaw

    package_root = package_root.resolve()
    provider = thaw(lock.provider) if hasattr(lock, "provider") else {}
    if not isinstance(provider, dict):
        provider = {}
    dockerfile_rel = str(provider.get("dockerfile") or "environment/Dockerfile")
    platform = str(provider.get("platform") or "linux/arm64")
    # Official base (FROM bora-attempt:l1) then package Dockerfile → Attempt image.
    ensure_base_image(Path.cwd())
    short = lock.digest.replace("sha256:", "")[:12]
    tag = f"bora-pkg:{lock.task_id}-{short}"
    pkg_image = build_package_image(
        package_root=package_root,
        dockerfile_rel=dockerfile_rel,
        platform=platform,
        tag=tag,
        repo_root=Path.cwd(),
    )
    # Lifecycle prepare + image_contribute consume (fail closed).
    hook_prepare(lock, {"phase": "l1_prepare", "package_image": pkg_image.image_tag})
    try:
        pkg_image, contribute_meta = apply_image_contribute_bake(
            lock=lock,
            base_image=pkg_image,
            platform=platform,
        )
    except ImageContributeError as exc:
        raise RuntimeError(f"{exc.kind}:{exc.message}") from exc

    lock_path = Path.cwd() / ".bora" / "runtime-images" / "provider-l1.json"
    if not lock_path.is_file():
        lock_path = ensure_image_lock(Path.cwd())
    docker = DockerProvider(image_lock_path=lock_path)
    work = run_dir / "l1-work"
    if work.exists():
        shutil.rmtree(work)
    runtime = docker.prepare(
        attempt,
        package_root=package_root,
        work_root=work,
        network_mode=network_mode,
        hide_evaluation=True,
        image_lock=pkg_image,
    )
    meta = {
        "containment": "full_l1_attempt",
        "image": runtime.image_lock.image_digest if runtime.image_lock else "",
        "image_tag": runtime.image_lock.image_tag if runtime.image_lock else "",
        "package_dockerfile": dockerfile_rel,
        "platform": runtime.image_lock.platform if runtime.image_lock else "",
        "attempt_id": attempt.value,
        "policy": dict(runtime.policy_digests),
        "image_contribute": contribute_meta,
    }
    return docker, runtime, meta


def seed_l1_workspace(
    *,
    package_root: Path,
    workspace_host: Path,
    allow_offline_agent: bool,
    l1_meta: dict[str, Any],
) -> None:
    """Seed Attempt workspace from package data/ and optional solution/."""
    workspace_host.mkdir(parents=True, exist_ok=True)
    data_dir = package_root / "data"
    if data_dir.is_dir():
        for src in data_dir.iterdir():
            if src.is_file():
                shutil.copy2(src, workspace_host / src.name)
    # Isolation / offline fixture: copy solution/* into workspace without Runtime invoke.
    if allow_offline_agent or os.environ.get("BORA_L1_USE_SOLUTION") == "1":
        solution_dir = package_root / "solution"
        if solution_dir.is_dir():
            for src in solution_dir.iterdir():
                if src.is_file():
                    shutil.copy2(src, workspace_host / src.name)
            l1_meta["solution_seed"] = True


def make_l1_placement_resolver(*, ledger: Any) -> Any:
    """Resolve Core-owned L1 placement from the prepare ledger.

    Plugins attach via ``ExecutorSPI.bind_to_target``. This helper only
    validates target/generation and returns ``TargetPlacement``.
    """

    def resolve_placement(binding: Any) -> Any:
        from bora.adapters.agent_container import effective_run_gid
        from bora.plugins.protocol import TargetPlacement

        actor_id = binding.actor_id
        if not actor_id:
            raise RuntimeError("actor_id_required")
        phys = ledger.actors.get(actor_id)
        if phys is None:
            raise RuntimeError("unknown_actor")
        target = ledger.targets.get(phys.target_id)
        if target is None or target.state != "ready" or not target.container_id:
            raise RuntimeError("target_dead")
        if binding.generation is not None and binding.generation != target.generation:
            raise RuntimeError("generation_mismatch")
        if binding.target_id and binding.target_id != target.target_id:
            raise RuntimeError("target_mismatch")
        return TargetPlacement(
            container_id=str(target.container_id),
            uid=int(phys.uid),
            gid=int(effective_run_gid(phys)),
            workdir="/attempt/workspace",
            home=str(getattr(phys, "home_container", None) or "/attempt/home"),
            shared_write=bool(getattr(phys, "shared_write", False)),
            shared_gid=getattr(phys, "shared_gid", None),
        )

    return resolve_placement
