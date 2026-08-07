"""Docker image lock resolution and package Attempt image builds."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from bora.adapters.provider_docker.errors import ProviderL1Error
from bora.adapters.provider_docker.types import DockerImageLock


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
    build_input = hashlib.sha256(df.read_bytes()).hexdigest()
    return DockerImageLock(
        kind="docker-package-attempt",
        platform=platform,
        image_tag=tag,
        image_digest=image_digest,
        build_input_digest=f"sha256:{build_input}",
    )


def sys_executable() -> str:
    return sys.executable
