"""Shared PATH probe for executor / ACP inventory (single shutil.which seam)."""

from __future__ import annotations

import shutil
from collections.abc import Callable

WhichFn = Callable[[str], str | None]


def probe_commands(
    candidates: tuple[str, ...],
    *,
    which: WhichFn | None = None,
) -> tuple[str | None, str | None]:
    """Return ``(first_candidate_or_hit_name, resolved_path_or_None)``."""
    which_fn = which or shutil.which
    for name in candidates:
        hit = which_fn(name)
        if hit:
            return name, hit
    return (candidates[0] if candidates else None), None
