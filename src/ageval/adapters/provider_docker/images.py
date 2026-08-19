"""Docker image lock resolution and package Attempt image builds."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from ageval.adapters.provider_docker.errors import ProviderL1Error
from ageval.adapters.provider_docker.official_base import (
    official_attempt_dir,
    official_build_input_digest,
    prepare_official_build_env,
)
from ageval.adapters.provider_docker.types import DockerImageLock

_OFFICIAL_BASE_TAG = "ageval-attempt:l1"
_COPY_HEAD = re.compile(r"^(COPY|ADD)\s+", re.IGNORECASE)
_SKIP_COPY_DIR_NAMES = frozenset({".ageval", ".git", "__pycache__", "node_modules"})
_INSPECT_DIGEST_FMT = "{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}"


def _official_lock_reusable(lock_path: Path, expected_digest: str) -> bool:
    """True when lock digest matches current inputs and the tagged image exists."""
    if not lock_path.is_file():
        return False
    try:
        lock = DockerImageLock.load(lock_path)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    if lock.build_input_digest != expected_digest:
        return False
    tag = lock.image_tag or _OFFICIAL_BASE_TAG
    return inspect_image_digest(tag) is not None


def ensure_image_lock(repo_root: Path | None = None) -> Path:
    """Build official base image lock if missing or inputs changed; return path."""
    root = repo_root or Path.cwd()
    lock_path = root / ".ageval" / "runtime-images" / "provider-l1.json"
    apt_mirror, pip_index = prepare_official_build_env(root)
    expected = "sha256:" + official_build_input_digest(
        official_attempt_dir(root),
        apt_mirror=apt_mirror,
        pip_index=pip_index,
    )
    if _official_lock_reusable(lock_path, expected):
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
    """Ensure official ``ageval-attempt:l1`` exists and return its lock record."""
    path = ensure_image_lock(repo_root)
    return DockerImageLock.load(path)


def dockerfile_logical_lines(text: str) -> list[str]:
    """Join backslash-continued Dockerfile lines; drop comments and blanks."""
    lines: list[str] = []
    buf: list[str] = []
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buf.append(stripped[:-1].rstrip())
            continue
        buf.append(stripped)
        joined = " ".join(part.strip() for part in buf if part.strip())
        buf = []
        if not joined or joined.startswith("#"):
            continue
        lines.append(joined)
    if buf:
        joined = " ".join(part.strip() for part in buf if part.strip())
        if joined and not joined.startswith("#"):
            lines.append(joined)
    return lines


def parse_dockerfile_from_image(text: str) -> str | None:
    """Return the first FROM image ref (skip scratch and substitution)."""
    for line in dockerfile_logical_lines(text):
        if not line.upper().startswith("FROM "):
            continue
        tokens = [t for t in line.split()[1:] if not t.startswith("-")]
        if not tokens:
            return None
        image = tokens[0]
        if image.upper() == "SCRATCH" or image.startswith("$"):
            return None
        return image
    return None


def parse_dockerfile_copy_sources(text: str) -> list[str]:
    """COPY/ADD source paths in build context. Skip ``--from`` multi-stage copies."""
    sources: list[str] = []
    for line in dockerfile_logical_lines(text):
        if not _COPY_HEAD.match(line):
            continue
        rest = _COPY_HEAD.sub("", line).strip()
        if re.search(r"--from=", rest, flags=re.IGNORECASE):
            continue
        if rest.startswith("["):
            try:
                arr = json.loads(rest)
            except json.JSONDecodeError:
                continue
            if isinstance(arr, list) and len(arr) >= 2:
                sources.extend(str(item) for item in arr[:-1])
            continue
        try:
            tokens = shlex.split(rest)
        except ValueError:
            continue
        tokens = [t for t in tokens if not t.startswith("-")]
        if len(tokens) >= 2:
            sources.extend(tokens[:-1])
    return sources


def _is_skipped_copy_path(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    if any(part in _SKIP_COPY_DIR_NAMES for part in rel.parts):
        return True
    return path.suffix == ".pyc" or path.name == ".DS_Store"


def hash_copy_sources(context_root: Path, sources: Iterable[str], hasher: hashlib._Hash) -> None:
    """Hash COPY/ADD sources under *context_root* in stable order."""
    root = context_root.resolve()
    seen: set[str] = set()
    for src in sources:
        rel = src.lstrip("./")
        if not rel or rel.startswith("/"):
            continue
        if any(ch in rel for ch in "*?["):
            matches = sorted(p for p in root.glob(rel) if p.exists())
        else:
            candidate = root / rel
            matches = [candidate] if candidate.exists() else []
        for path in matches:
            try:
                resolved = path.resolve()
                resolved.relative_to(root)
            except ValueError:
                continue
            files: list[Path]
            if resolved.is_file():
                files = [resolved]
            elif resolved.is_dir():
                files = sorted(p for p in resolved.rglob("*") if p.is_file())
            else:
                continue
            for file_path in files:
                if _is_skipped_copy_path(file_path, root):
                    continue
                key = str(file_path.relative_to(root)).replace("\\", "/")
                if key in seen:
                    continue
                seen.add(key)
                hasher.update(key.encode("utf-8"))
                hasher.update(b"\0")
                hasher.update(file_path.read_bytes())
                hasher.update(b"\0")


def package_image_content_digest(
    *,
    dockerfile: Path,
    package_root: Path,
    platform: str,
    base_digest: str,
) -> str:
    """Hex digest of Dockerfile + FROM base digest + COPY set + platform."""
    text = dockerfile.read_bytes()
    hasher = hashlib.sha256()
    hasher.update(b"dockerfile\0")
    hasher.update(text)
    hasher.update(b"\0base\0")
    hasher.update(base_digest.encode("utf-8"))
    hasher.update(b"\0platform\0")
    hasher.update(platform.encode("utf-8"))
    hasher.update(b"\0copy\0")
    hash_copy_sources(
        package_root,
        parse_dockerfile_copy_sources(text.decode("utf-8")),
        hasher,
    )
    return hasher.hexdigest()


def official_base_digest(repo_root: Path | None = None) -> str:
    """Official ``ageval-attempt:l1`` digest from the lock (stable; not a fresh inspect)."""
    lock = ensure_base_image(repo_root)
    return lock.image_digest or lock.build_input_digest


def resolve_from_base_digest(dockerfile_text: str, repo_root: Path | None = None) -> str:
    """Base identity for the content key.

    ``FROM ageval-attempt:l1`` uses the official lock digest so a rebuilt base
    invalidates package tags. Other FROM refs stay the Dockerfile text (already
    hashed); do not inspect them — first-build inspect would change the key.
    """
    ref = parse_dockerfile_from_image(dockerfile_text)
    if ref is None:
        return ""
    image = ref.rsplit("/", 1)[-1]
    if image == _OFFICIAL_BASE_TAG or ref == _OFFICIAL_BASE_TAG:
        return official_base_digest(repo_root)
    return ref


def package_local_tag(content_digest: str) -> str:
    return f"ageval-pkg:{content_digest[:12]}"


def is_official_base_noop_dockerfile(text: str) -> bool:
    """True when the Dockerfile is only ``FROM ageval-attempt:l1`` (optional AS)."""
    lines = dockerfile_logical_lines(text)
    if len(lines) != 1:
        return False
    line = lines[0]
    if not line.upper().startswith("FROM "):
        return False
    tokens = [t for t in line.split()[1:] if not t.startswith("-")]
    if not tokens:
        return False
    image = tokens[0]
    if image != _OFFICIAL_BASE_TAG and image.rsplit("/", 1)[-1] != _OFFICIAL_BASE_TAG:
        return False
    extra = tokens[1:]
    if not extra:
        return True
    return len(extra) == 2 and extra[0].upper() == "AS"


def inspect_image_digest(tag: str) -> str | None:
    """Evidence digest for an existing local tag, or None if missing."""
    proc = subprocess.run(
        ["docker", "image", "inspect", tag, "--format", _INSPECT_DIGEST_FMT],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    digest = (proc.stdout or "").strip()
    return digest or None


def build_package_image(
    *,
    package_root: Path,
    dockerfile_rel: str = "environment/Dockerfile",
    platform: str = "linux/arm64",
    tag: str | None = None,
    repo_root: Path | None = None,
) -> DockerImageLock:
    """Build Attempt image from package Dockerfile (context = package root).

    Cache key is Dockerfile + FROM base digest + COPY set + platform — not
    ``lock.digest`` or ``task_id``. Existing ``ageval-pkg:{content[:12]}`` tags
    skip ``buildx --load``.
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
    text = df.read_text(encoding="utf-8")
    base_digest = resolve_from_base_digest(text, repo_root)
    content = package_image_content_digest(
        dockerfile=df,
        package_root=package_root,
        platform=platform,
        base_digest=base_digest,
    )
    tag = tag or package_local_tag(content)
    existing = inspect_image_digest(tag)
    if existing is not None:
        return DockerImageLock(
            kind="docker-package-attempt",
            platform=platform,
            image_tag=tag,
            image_digest=existing,
            build_input_digest=f"sha256:{content}",
        )

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

    image_digest = inspect_image_digest(tag)
    if not image_digest:
        raise ProviderL1Error("image_unresolved", "cannot inspect package image")
    return DockerImageLock(
        kind="docker-package-attempt",
        platform=platform,
        image_tag=tag,
        image_digest=image_digest,
        build_input_digest=f"sha256:{content}",
    )


def sys_executable() -> str:
    return sys.executable
