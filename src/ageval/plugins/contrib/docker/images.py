"""Images the docker box runs: the official base, then the task's own recipe.

The cache key is the recipe plus what it copies, never the task id or the lock
digest — two tasks with the same recipe share one image, and editing the recipe
invalidates it.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from ageval.environments.protocol import EnvironmentFailure

BASE_TAG = "ageval-attempt:base"
PACKAGE_TAG_PREFIX = "ageval-pkg"
BASE_LOCK_PATH = Path(".ageval") / "runtime-images" / "attempt-base.json"

_COPY_HEAD = re.compile(r"^(COPY|ADD)\s+", re.IGNORECASE)
_SKIP_COPY_NAMES = frozenset({".ageval", ".git", "__pycache__", "node_modules"})
_DIGEST_FORMAT = "{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}"


def docker(*args: str, timeout: float = 600.0) -> subprocess.CompletedProcess[str]:
    """Run one docker CLI command with the parent's daemon environment."""
    return subprocess.run(  # noqa: S603 — argv is built here, never a shell string
        ["docker", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def daemon_available() -> bool:
    return docker("version", "--format", "{{.Server.Version}}", timeout=30.0).returncode == 0


def image_digest(tag: str) -> str | None:
    """Digest of an existing local tag, or None when it is not there."""
    found = docker("image", "inspect", tag, "--format", _DIGEST_FORMAT, timeout=60.0)
    if found.returncode != 0:
        return None
    return (found.stdout or "").strip() or None


def ensure_base_image(repo_root: Path) -> str:
    """Digest of the official base image, building it when absent.

    The base bakes the ACP entries, so a run must never fall back to installing
    an agent at invoke time.
    """
    digest = image_digest(BASE_TAG)
    if digest is not None:
        return digest
    build_script = repo_root / "docker" / "attempt" / "build.py"
    if not build_script.is_file():
        raise EnvironmentFailure(
            "environment_image_unresolved",
            f"{BASE_TAG} is missing and {build_script} is not in this checkout",
        )
    built = subprocess.run(  # noqa: S603 — repo-local build entrypoint
        [
            sys.executable,
            str(build_script),
            "--tag",
            BASE_TAG,
            "--output-lock",
            str(repo_root / BASE_LOCK_PATH),
        ],
        check=False,
        cwd=str(repo_root),
    )
    digest = image_digest(BASE_TAG)
    if built.returncode != 0 or digest is None:
        raise EnvironmentFailure(
            "environment_image_unresolved",
            f"could not build the official base image {BASE_TAG}",
        )
    return digest


def resolve_image(
    *,
    task_root: Path,
    repo_root: Path,
    dockerfile_rel: str | None,
    declared_image: str | None,
    platform: str,
    force_build: bool,
) -> tuple[str, str]:
    """Return ``(tag, digest)`` for this Attempt's image.

    A declared ``docker_image`` is used as-is. A task recipe is built on top of
    the official base. With neither, the base itself is the box.
    """
    if declared_image:
        digest = image_digest(declared_image)
        if digest is None:
            pulled = docker("pull", declared_image)
            digest = image_digest(declared_image)
            if digest is None:
                raise EnvironmentFailure(
                    "environment_image_unresolved",
                    f"cannot resolve image {declared_image!r}: "
                    f"{(pulled.stderr or '').strip()[-300:]}",
                )
        return declared_image, digest

    base_digest = ensure_base_image(repo_root)
    if dockerfile_rel is None:
        return BASE_TAG, base_digest
    return build_task_image(
        task_root=task_root,
        dockerfile_rel=dockerfile_rel,
        platform=platform,
        base_digest=base_digest,
        force_build=force_build,
    )


def build_task_image(
    *,
    task_root: Path,
    dockerfile_rel: str,
    platform: str,
    base_digest: str,
    force_build: bool,
) -> tuple[str, str]:
    """Build the task recipe with the task directory as build context."""
    dockerfile = (task_root / dockerfile_rel).resolve()
    try:
        dockerfile.relative_to(task_root.resolve())
    except ValueError as exc:
        raise EnvironmentFailure(
            "environment_image_unresolved",
            f"recipe outside the task directory: {dockerfile_rel}",
        ) from exc
    if not dockerfile.is_file():
        raise EnvironmentFailure(
            "environment_image_unresolved",
            f"missing task recipe: {dockerfile_rel}",
        )

    content = content_digest(
        dockerfile=dockerfile,
        context_root=task_root,
        platform=platform,
        base_digest=base_digest,
    )
    tag = f"{PACKAGE_TAG_PREFIX}:{content[:12]}"
    if not force_build:
        existing = image_digest(tag)
        if existing is not None:
            return tag, existing

    built = docker(
        "buildx",
        "build",
        "--platform",
        platform,
        "-f",
        str(dockerfile),
        "-t",
        tag,
        "--load",
        str(task_root),
    )
    digest = image_digest(tag)
    if built.returncode != 0 or digest is None:
        raise EnvironmentFailure(
            "environment_image_unresolved",
            f"task image build failed: {(built.stderr or built.stdout or '')[-2000:]}",
        )
    return tag, digest


def content_digest(
    *,
    dockerfile: Path,
    context_root: Path,
    platform: str,
    base_digest: str,
) -> str:
    """Recipe + base identity + copied bytes + platform."""
    text = dockerfile.read_bytes()
    hasher = hashlib.sha256()
    for label, payload in (
        (b"dockerfile", text),
        (b"base", base_digest.encode("utf-8")),
        (b"platform", platform.encode("utf-8")),
    ):
        hasher.update(label + b"\0" + payload + b"\0")
    _hash_copy_sources(context_root, copy_sources(text.decode("utf-8")), hasher)
    return hasher.hexdigest()


def logical_lines(text: str) -> list[str]:
    """Dockerfile lines with continuations joined and comments dropped."""
    lines: list[str] = []
    buffer: list[str] = []
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buffer.append(stripped[:-1].rstrip())
            continue
        buffer.append(stripped)
        joined = " ".join(part.strip() for part in buffer if part.strip())
        buffer = []
        if joined and not joined.startswith("#"):
            lines.append(joined)
    joined = " ".join(part.strip() for part in buffer if part.strip())
    if joined and not joined.startswith("#"):
        lines.append(joined)
    return lines


def copy_sources(text: str) -> list[str]:
    """COPY/ADD sources in the build context (multi-stage copies excluded)."""
    sources: list[str] = []
    for line in logical_lines(text):
        if not _COPY_HEAD.match(line):
            continue
        rest = _COPY_HEAD.sub("", line).strip()
        if re.search(r"--from=", rest, flags=re.IGNORECASE):
            continue
        if rest.startswith("["):
            try:
                parsed = json.loads(rest)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list) and len(parsed) >= 2:
                sources.extend(str(item) for item in parsed[:-1])
            continue
        try:
            tokens = [t for t in shlex.split(rest) if not t.startswith("-")]
        except ValueError:
            continue
        if len(tokens) >= 2:
            sources.extend(tokens[:-1])
    return sources


def _hash_copy_sources(
    context_root: Path,
    sources: Iterable[str],
    hasher: hashlib._Hash,
) -> None:
    root = context_root.resolve()
    seen: set[str] = set()
    for source in sources:
        rel = source.lstrip("./")
        if not rel or rel.startswith("/"):
            continue
        matches = (
            sorted(p for p in root.glob(rel) if p.exists())
            if any(ch in rel for ch in "*?[")
            else [root / rel]
        )
        for match in matches:
            for path in _files_under(match, root):
                key = str(path.relative_to(root)).replace("\\", "/")
                if key in seen:
                    continue
                seen.add(key)
                hasher.update(key.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")


def _files_under(path: Path, root: Path) -> Sequence[Path]:
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (ValueError, OSError):
        return ()
    if resolved.is_file():
        return () if _skipped(resolved, root) else (resolved,)
    if not resolved.is_dir():
        return ()
    return [p for p in sorted(resolved.rglob("*")) if p.is_file() and not _skipped(p, root)]


def _skipped(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    if any(part in _SKIP_COPY_NAMES for part in rel.parts):
        return True
    return path.suffix == ".pyc" or path.name == ".DS_Store"
