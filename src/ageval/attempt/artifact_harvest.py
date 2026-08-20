"""Collect declared artifacts from the box after writers stop.

``run.py`` is a parent process. Agent writes live in the box. Shared-FS kinds
already have those bytes on the parent dest when the task published; remote
kinds do not. This step fills *missing* publishable files via Protocol
``download`` from ``/attempt/workspace/<basename>``. It does not scrape chat
and does not run on every invoke.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ageval.config.model import thaw
from ageval.environments.protocol import WORKSPACE_PATH, EnvironmentFailure


async def harvest_workspace_artifacts(ctx: Any) -> None:
    """Copy missing publishable artifacts from the box workspace onto evidence."""
    ctx.assert_writers_stopped()
    caps = getattr(ctx.host, "capabilities", None)
    if caps is not None and not getattr(caps, "download", False):
        return
    refs = thaw(getattr(ctx.lock, "resolved_references", None) or {})
    declared = refs.get("artifacts") if isinstance(refs, dict) else None
    if not isinstance(declared, list) or not declared:
        return
    staged = ctx.evidence.path("task-artifacts")
    staged.mkdir(parents=True, exist_ok=True)
    pulled: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    for item in declared:
        if not isinstance(item, dict):
            continue
        aid = str(item.get("id") or "").strip()
        rel = str(item.get("path") or "").strip()
        if not aid or not rel:
            continue
        name = Path(rel).name
        dest = staged / f"{aid}{Path(name).suffix or '.json'}"
        if dest.is_file():
            skipped.append(aid)
            continue
        source = f"{WORKSPACE_PATH}/{name}"
        try:
            await ctx.host.download(source, dest)
        except EnvironmentFailure:
            missing.append(aid)
            continue
        pulled.append(aid)
    ctx.record_fact(
        "artifacts_harvested",
        {"pulled": pulled, "skipped": skipped, "missing": missing},
    )
