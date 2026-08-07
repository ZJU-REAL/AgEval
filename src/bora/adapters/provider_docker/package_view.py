"""Host-side package tree filters for L1 mounts (hide evaluation/)."""

from __future__ import annotations

import shutil
from pathlib import Path


def copy_package_filtered(src: Path, dest: Path) -> None:
    """Copy package tree excluding evaluation/ and common gold locations."""
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        name = item.name
        if name in {"evaluation", ".bora", "__pycache__"}:
            continue
        target = dest / name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
