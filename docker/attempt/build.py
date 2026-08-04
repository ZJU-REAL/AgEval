"""Build and lock the repository-owned L1 Attempt image.

Usage:
  uv run python docker/attempt/build.py --platform linux/arm64 \\
      --output-lock .bora/runtime-images/provider-l1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# Spec 19: digest must cover Dockerfile + install script + pin lock (not Dockerfile alone).
_BUILD_INPUT_NAMES = (
    "Dockerfile",
    "install-executors.sh",
    "acp-entries.lock.json",
)


def _build_input_digest(attempt_dir: Path) -> str:
    h = hashlib.sha256()
    for name in _BUILD_INPUT_NAMES:
        path = attempt_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"missing build input: {path}")
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


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

    root = Path(__file__).resolve().parents[2]
    attempt_dir = root / "docker" / "attempt"
    dockerfile = attempt_dir / "Dockerfile"
    if not dockerfile.is_file():
        print(f"missing Dockerfile: {dockerfile}", file=sys.stderr)
        return 2

    try:
        build_input = _build_input_digest(attempt_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    pin_lock = attempt_dir / "acp-entries.lock.json"
    pin_doc = json.loads(pin_lock.read_text(encoding="utf-8"))

    cmd = [
        "docker",
        "buildx",
        "build",
        "--platform",
        args.platform,
        "-f",
        str(dockerfile),
        "-t",
        args.tag,
        "--load",
        str(attempt_dir),
    ]
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
        "build_input_files": list(_BUILD_INPUT_NAMES),
        "acp_entries_lock": pin_doc,
        "generator": "docker/attempt/build.py",
        "runtime_abi": "python3.12",
        "actor_uid_path_probe": "ok",
    }
    args.output_lock.parent.mkdir(parents=True, exist_ok=True)
    args.output_lock.write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(lock, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
