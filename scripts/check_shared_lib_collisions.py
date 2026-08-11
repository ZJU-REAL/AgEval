#!/usr/bin/env python3
"""Acceptance gate: Dataset shared/lib vs task lib top-level name collisions (#65).

Usage::

    uv run python scripts/check_shared_lib_collisions.py <database-root> [...]
    uv run python scripts/check_shared_lib_collisions.py examples/core

Exit codes:
  0 — no shared/ or no collisions / forbidden paths
  1 — collision or forbidden shared/ layout
  2 — usage / invalid path
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed when shared/lib collides with task lib top-level names (#65)."
    )
    parser.add_argument(
        "database_roots",
        nargs="+",
        type=Path,
        help="Database root(s) containing bora.yaml",
    )
    args = parser.parse_args(argv)

    # Prefer installed package when run via uv/repo root.
    repo = Path(__file__).resolve().parents[1]
    src = repo / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from bora.config.errors import ConfigError
    from bora.config.shared import find_lib_collisions, validate_shared_layout

    failed = 0
    for raw in args.database_roots:
        root = raw.expanduser().resolve(strict=False)
        if not (root / "bora.yaml").is_file():
            print(f"FAIL {root}: missing bora.yaml", file=sys.stderr)
            failed += 1
            continue
        try:
            validate_shared_layout(root)
        except ConfigError as exc:
            print(f"FAIL {root}: {exc.message} ({exc.location})", file=sys.stderr)
            failed += 1
            continue
        hits = find_lib_collisions(root)
        if hits:
            # validate_shared_layout should have raised; belt-and-suspenders.
            for name, shared_loc, task_loc in hits:
                print(
                    f"FAIL {root}: collision {name!r} in {shared_loc} and {task_loc}",
                    file=sys.stderr,
                )
            failed += 1
            continue
        shared = root / "shared"
        if shared.is_dir():
            print(f"OK   {root}: shared/ present, no lib collisions")
        else:
            print(f"OK   {root}: no shared/ (noop)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
