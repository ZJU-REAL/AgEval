"""Build and lock the repository-owned L1 Attempt image.

Usage:
  uv run python docker/attempt/build.py --platform linux/arm64 \\
      --output-lock .ageval/runtime-images/provider-l1.json

``--python-version`` selects the base CPython minor (default 3.12). The
Dockerfile resolves ``FROM python:${PYTHON_VERSION}-slim-bookworm``; a
non-default version also switches the default ``--tag`` to the versioned
``ageval-attempt:py<version>`` so bases coexist instead of overwriting.

Optional process / host-env knobs (empty = official Debian / PyPI):

  AGEVAL_APT_MIRROR   e.g. http://mirrors.aliyun.com/debian
  AGEVAL_PIP_INDEX    e.g. https://pypi.tuna.tsinghua.edu.cn/simple
                      (plugin bake layers read the same knob)

``ageval run`` already loads Database / cwd / repo ``.env`` before prepare.
This script loads the same host env files when the package is importable.
Dataset ``.env`` is applied by ``ageval run``, not by a bare invocation here.
Do not put these knobs in ``~/.zshrc`` — process env would mask Dataset ``.env``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

BUILD_INPUT_NAMES = ("Dockerfile", "install-executors.sh", "acp-entries.lock.json")
DEFAULT_PYTHON_VERSION = "3.12"
_PYTHON_VERSION_RE = re.compile(r"^\d+\.\d+$")


def valid_python_version(text: str) -> bool:
    """A CPython minor like ``3.13``; ``latest`` / ``3`` / empty are not."""
    return _PYTHON_VERSION_RE.fullmatch(text) is not None


def versioned_tag(version: str) -> str:
    return f"ageval-attempt:py{version}"


def default_tag(python_version: str) -> str:
    """3.12 keeps the historical ``l1`` tag; other versions get their own."""
    if python_version == DEFAULT_PYTHON_VERSION:
        return "ageval-attempt:l1"
    return versioned_tag(python_version)


def official_attempt_dir(root: Path) -> Path:
    return root / "docker" / "attempt"


def prepare_official_build_env(root: Path) -> tuple[str, str]:
    del root
    return (os.environ.get("AGEVAL_APT_MIRROR") or "").strip(), (
        os.environ.get("AGEVAL_PIP_INDEX") or ""
    ).strip()


def official_build_input_digest(
    attempt_dir: Path, *, apt_mirror: str, pip_index: str, python_version: str
) -> str:
    hasher = hashlib.sha256()
    hasher.update(f"{apt_mirror}\n{pip_index}\n{python_version}\n".encode())
    for name in BUILD_INPUT_NAMES:
        path = attempt_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"missing build input: {path}")
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def official_buildx_command(
    *,
    dockerfile: Path,
    tag: str,
    platform: str,
    context: Path,
    apt_mirror: str,
    pip_index: str,
    python_version: str,
) -> list[str]:
    cmd = ["docker", "build", "--platform", platform, "-f", str(dockerfile), "-t", tag]
    if apt_mirror:
        cmd.extend(["--build-arg", f"AGEVAL_APT_MIRROR={apt_mirror}"])
    if pip_index:
        cmd.extend(["--build-arg", f"AGEVAL_PIP_INDEX={pip_index}"])
    cmd.extend(["--build-arg", f"PYTHON_VERSION={python_version}"])
    cmd.append(str(context))
    return cmd


def _load_host_env(repo_root: Path) -> None:
    try:
        from ageval.application.attempt.env_bootstrap import load_host_env_files
    except ImportError:
        return
    load_host_env_files(package_root=repo_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="linux/arm64")
    parser.add_argument(
        "--python-version",
        default=DEFAULT_PYTHON_VERSION,
        help="base CPython minor, e.g. 3.13 (default 3.12)",
    )
    parser.add_argument(
        "--output-lock",
        type=Path,
        default=Path(".ageval/runtime-images/provider-l1.json"),
    )
    parser.add_argument("--tag", default=None)
    args = parser.parse_args(argv)

    python_version = args.python_version.strip()
    if not valid_python_version(python_version):
        print(
            f"invalid --python-version {args.python_version!r}: expected a CPython minor like 3.13",
            file=sys.stderr,
        )
        return 2

    tag = args.tag
    if tag is None:
        tag = default_tag(python_version)

    root = _REPO_ROOT
    attempt_dir = official_attempt_dir(root)
    dockerfile = attempt_dir / "Dockerfile"
    if not dockerfile.is_file():
        print(f"missing Dockerfile: {dockerfile}", file=sys.stderr)
        return 2

    _load_host_env(root)
    apt_mirror, pip_index = prepare_official_build_env(root)
    try:
        build_input = official_build_input_digest(
            attempt_dir,
            apt_mirror=apt_mirror,
            pip_index=pip_index,
            python_version=python_version,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    pin_lock = attempt_dir / "acp-entries.lock.json"
    pin_doc = json.loads(pin_lock.read_text(encoding="utf-8"))

    cmd = official_buildx_command(
        dockerfile=dockerfile,
        tag=tag,
        platform=args.platform,
        context=attempt_dir,
        apt_mirror=apt_mirror,
        pip_index=pip_index,
        python_version=python_version,
    )
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode

    inspect = subprocess.run(
        ["docker", "image", "inspect", tag, "--format", "{{json .Id}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspect.returncode != 0:
        print(inspect.stderr, file=sys.stderr)
        return inspect.returncode
    image_id = json.loads(inspect.stdout.strip())
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
    image_digest = (dig.stdout or image_id).strip()

    # Actor-UID PATH probe for five ACP entries (image already verified in Dockerfile).
    probe = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "10001:10001",
            tag,
            "bash",
            "-c",
            "command -v codex && command -v codex-acp && "
            "command -v pi && command -v pi-acp && "
            "command -v opencode && "
            "(command -v claude || command -v claude-code) && command -v claude-agent-acp && "
            "command -v grok",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        print(probe.stderr or probe.stdout, file=sys.stderr)
        print("post-build actor UID PATH probe failed", file=sys.stderr)
        return probe.returncode or 1

    lock = {
        "kind": "docker-attempt",
        "platform": args.platform,
        "python_version": python_version,
        "image_tag": tag,
        "image_id": image_id,
        "image_digest": image_digest,
        "build_input_digest": f"sha256:{build_input}",
        "build_input_files": list(BUILD_INPUT_NAMES),
        "acp_entries_lock": pin_doc,
        "generator": "docker/attempt/build.py",
        "runtime_abi": f"python{python_version}",
        "actor_uid_path_probe": "ok",
    }
    args.output_lock.parent.mkdir(parents=True, exist_ok=True)
    args.output_lock.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(lock, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
