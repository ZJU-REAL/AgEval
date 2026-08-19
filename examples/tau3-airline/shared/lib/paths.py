"""Dataset path helpers (#65: shared/lib + shared/assets)."""

from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    """Database root: ``shared/lib/paths.py`` → parents[2]."""
    here = Path(__file__).resolve()
    # .../shared/lib/paths.py
    if here.parent.name == "lib" and here.parents[1].name == "shared":
        return here.parents[2]
    # Fallback: walk up for ageval.yaml
    for parent in here.parents:
        if (parent / "ageval.yaml").is_file():
            return parent
    return here.parents[2]


def assets_root() -> Path:
    """Domain assets under ``shared/assets/`` (in packageDigest)."""
    return package_root() / "shared" / "assets"
