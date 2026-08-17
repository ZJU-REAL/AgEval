"""Build and lock the repository-owned L1 Attempt image.

Usage:
  uv run python docker/attempt/build.py --platform linux/arm64 \\
      --output-lock .bora/runtime-images/provider-l1.json

Optional process / host-env knobs (empty = official Debian / PyPI):

  BORA_APT_MIRROR   e.g. http://mirrors.aliyun.com/debian
  BORA_PIP_INDEX    e.g. https://pypi.tuna.tsinghua.edu.cn/simple

``bora run`` already loads Database / cwd / repo ``.env`` before prepare.
This script loads the same host env files when the package is importable.
Dataset ``.env`` is applied by ``bora run``, not by a bare invocation here.
Do not put these knobs in ``~/.zshrc`` — process env would mask Dataset ``.env``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bora.adapters.provider_docker.official_base import (  # noqa: E402
    BUILD_INPUT_NAMES,
    official_attempt_dir,
    official_build_input_digest,
    official_buildx_command,
    prepare_official_build_env,
)


def _load_host_env(repo_root: Path) -> None:
    try:
        from bora.application.attempt.env_bootstrap import load_host_env_files
    except ImportError:
        return
    load_host_env_files(package_root=repo_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="linux/arm64")
    parser.add_argument(
        "--output-lock",
        type=Path,
        default=Path(".bora/runtime-images/provider-l1.json"),
    )
    parser.add_argument("--tag", default="bora-attempt:l1")
    args = parser.parse_args(argv)

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
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    pin_lock = attempt_dir / "acp-entries.lock.json"
    pin_doc = json.loads(pin_lock.read_text(encoding="utf-8"))

    cmd = official_buildx_command(
        dockerfile=dockerfile,
        tag=args.tag,
        platform=args.platform,
        context=attempt_dir,
        apt_mirror=apt_mirror,
        pip_index=pip_index,
    )
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode

    inspect = subprocess.run(
        ["docker", "image", "inspect", args.tag, "--format", "{{json .Id}}"],
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
            args.tag,
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
            args.tag,
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
        "image_tag": args.tag,
        "image_id": image_id,
        "image_digest": image_digest,
        "build_input_digest": f"sha256:{build_input}",
        "build_input_files": list(BUILD_INPUT_NAMES),
        "acp_entries_lock": pin_doc,
        "generator": "docker/attempt/build.py",
        "runtime_abi": "python3.12",
        "actor_uid_path_probe": "ok",
    }
    args.output_lock.parent.mkdir(parents=True, exist_ok=True)
    args.output_lock.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(lock, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
