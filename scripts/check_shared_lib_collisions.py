#!/usr/bin/env python3
"""Acceptance gate: Dataset shared/ layout + task top-level ``shared`` shadow (#68).

Usage::

    uv run python scripts/check_shared_lib_collisions.py <database-root> [...]
    uv run python scripts/check_shared_lib_collisions.py examples/datasets/tau3-airline

Exit codes:
  0 — no forbidden shared/ paths and no task-level ``shared`` shadow
  1 — forbidden layout or task ``shared`` shadow
  2 — usage / invalid path

Note: same module stem under ``shared/lib`` and ``tasks/*/lib`` is **allowed**
under namespaced imports (``shared.lib.x`` vs ``lib.x``). This script no longer
bans stem collisions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail closed on forbidden Dataset shared/ content or task-level "
            "top-level name 'shared' (#68)."
        )
    )
    parser.add_argument(
        "database_roots",
        nargs="+",
        type=Path,
        help="Database root(s) containing ageval.yaml",
    )
    args = parser.parse_args(argv)

    # Prefer installed package when run via uv/repo root.
    repo = Path(__file__).resolve().parents[1]
    src = repo / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from ageval.config.errors import ConfigError
    from ageval.config.shared import find_task_shared_shadows, validate_shared_layout

    failed = 0
    for raw in args.database_roots:
        root = raw.expanduser().resolve(strict=False)
        if not (root / "ageval.yaml").is_file():
            print(f"FAIL {root}: missing ageval.yaml", file=sys.stderr)
            failed += 1
            continue
        try:
            validate_shared_layout(root)
        except ConfigError as exc:
            print(f"FAIL {root}: {exc.message} ({exc.location})", file=sys.stderr)
            failed += 1
            continue
        # Belt-and-suspenders: report shadows even if validate missed them.
        shadows = find_task_shared_shadows(root)
        if shadows:
            for loc in shadows:
                print(f"FAIL {root}: task owns reserved name shared at {loc}", file=sys.stderr)
            failed += 1
            continue
        shared = root / "shared"
        if shared.is_dir():
            print(f"OK   {root}: shared/ present, no task 'shared' shadow")
        else:
            print(f"OK   {root}: no shared/, no task 'shared' shadow")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
