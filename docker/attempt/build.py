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
    dockerfile = root / "docker" / "attempt" / "Dockerfile"
    if not dockerfile.is_file():
        print(f"missing Dockerfile: {dockerfile}", file=sys.stderr)
        return 2

    # Build-input digest over Dockerfile bytes for reproducibility evidence.
    build_input = hashlib.sha256(dockerfile.read_bytes()).hexdigest()

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
        str(dockerfile.parent),
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
    # Prefer RepoDigests when available; else use image id.
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

    lock = {
        "kind": "docker-attempt",
        "platform": args.platform,
        "image_tag": args.tag,
        "image_id": image_id,
        "image_digest": image_digest,
        "build_input_digest": f"sha256:{build_input}",
        "generator": "docker/attempt/build.py",
        "runtime_abi": "python3.12",
    }
    args.output_lock.parent.mkdir(parents=True, exist_ok=True)
    args.output_lock.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(lock, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
