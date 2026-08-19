"""ageval — Bounded Orchestration for Runtime Agents.

Delivered checkpoints:
- v0.1 Config Core (``load_and_lock`` + ``ageval lock``)
- v0.2 Lifecycle Core (identity + coordinator; application probe, no ``ageval run``)

Evidence remains ``design-only`` until Roadmap product verticals land.
"""

from __future__ import annotations

from pathlib import Path


def _load_version() -> str:
    try:
        from importlib.metadata import version

        return version("ageval")
    except Exception:
        pass
    # Editable / source tree: repo-root VERSION (src/ageval/__init__.py → parents[2]).
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0"


__version__ = _load_version()
