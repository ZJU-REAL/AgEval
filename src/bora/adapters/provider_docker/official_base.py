"""Official L1 base image build inputs (files + optional apt/pip mirrors)."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

APT_MIRROR_ENV = "BORA_APT_MIRROR"
PIP_INDEX_ENV = "BORA_PIP_INDEX"
BUILD_INPUT_NAMES = (
    "Dockerfile",
    "install-executors.sh",
    "acp-entries.lock.json",
    "sitecustomize.py",
)

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def official_attempt_dir(repo_root: Path) -> Path:
    return repo_root / "docker" / "attempt"


def mirror_build_args() -> tuple[str, str]:
    """Current process-env mirror knobs (already-set values win)."""
    apt = (os.environ.get(APT_MIRROR_ENV) or "").strip()
    pip = (os.environ.get(PIP_INDEX_ENV) or "").strip()
    return apt, pip


def _strip_env_value(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if text[0] in "\"'" and len(text) >= 2 and text[-1] == text[0]:
        return text[1:-1]
    if " #" in text:
        text = text.split(" #", 1)[0].rstrip()
    return text


def absorb_mirror_env_files(*env_files: Path) -> None:
    """Fill unset ``BORA_APT_MIRROR`` / ``BORA_PIP_INDEX`` from dotenv files.

    Process env wins. Adapters do not import application ``load_host_env_files``;
    ``bora run`` already loaded Dataset / cwd / repo ``.env`` before prepare.
    """
    wanted = {APT_MIRROR_ENV, PIP_INDEX_ENV}
    for path in env_files:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _ENV_LINE.match(line)
            if not match:
                continue
            key, raw = match.group(1), match.group(2)
            if key not in wanted or key in os.environ:
                continue
            os.environ[key] = _strip_env_value(raw)


def prepare_official_build_env(repo_root: Path) -> tuple[str, str]:
    """Load cwd/repo ``.env`` for the two knobs, then return stripped values."""
    absorb_mirror_env_files(Path.cwd() / ".env", repo_root / ".env")
    return mirror_build_args()


def official_buildx_command(
    *,
    dockerfile: Path,
    tag: str,
    platform: str,
    context: Path,
    apt_mirror: str,
    pip_index: str,
) -> list[str]:
    """``docker buildx`` argv for the official base, including mirror build-args."""
    return [
        "docker",
        "buildx",
        "build",
        "--platform",
        platform,
        "-f",
        str(dockerfile),
        "-t",
        tag,
        "--build-arg",
        f"BORA_APT_MIRROR={apt_mirror}",
        "--build-arg",
        f"BORA_PIP_INDEX={pip_index}",
        "--load",
        str(context),
    ]


def official_build_input_digest(
    attempt_dir: Path,
    *,
    apt_mirror: str = "",
    pip_index: str = "",
) -> str:
    """Hex digest of official base files plus the two optional build-args."""
    hasher = hashlib.sha256()
    for name in BUILD_INPUT_NAMES:
        path = attempt_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"missing build input: {path}")
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    hasher.update(b"BORA_APT_MIRROR\0")
    hasher.update(apt_mirror.encode("utf-8"))
    hasher.update(b"\0BORA_PIP_INDEX\0")
    hasher.update(pip_index.encode("utf-8"))
    hasher.update(b"\0")
    return hasher.hexdigest()
