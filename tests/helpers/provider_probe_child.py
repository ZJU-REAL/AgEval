"""Test-only child workloads for Provider L0 probes. Never imported from src/."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="exit0")
    parser.add_argument("--path", default="")
    parser.add_argument("--seconds", type=float, default=2.0)
    args = parser.parse_args(argv)

    if args.mode == "exit0":
        if args.path:
            Path(args.path).write_text("ok\n", encoding="utf-8")
        print("hello-stdout")
        print("hello-stderr", file=sys.stderr)
        return 0

    if args.mode == "exit1":
        print("fail", file=sys.stderr)
        return 1

    if args.mode == "write-loop":
        path = Path(args.path)
        end = time.time() + args.seconds
        while time.time() < end:
            path.write_text(f"{time.time()}\n", encoding="utf-8")
            time.sleep(0.05)
        return 0

    if args.mode == "ignore-term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        path = Path(args.path)
        end = time.time() + args.seconds
        while time.time() < end:
            path.write_text(f"{time.time()}\n", encoding="utf-8")
            time.sleep(0.05)
        return 0

    if args.mode == "spawn-group-writer":
        # Fork a child that stays in the same process group and writes.
        path = Path(args.path)
        pid = os.fork()
        if pid == 0:
            # child writer
            end = time.time() + args.seconds
            while time.time() < end:
                path.write_text(f"{time.time()}\n", encoding="utf-8")
                time.sleep(0.05)
            os._exit(0)
        # parent waits a bit then exits; writer may remain in group
        time.sleep(0.1)
        return 0

    print(f"unknown mode {args.mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
