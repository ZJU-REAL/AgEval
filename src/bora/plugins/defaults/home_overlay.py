"""Core default ``home_overlay`` handler.

Creates the cred tree, lets plugins write extras, then copies into actor HOME.
Plugins must not call Docker or invent PASS.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from bora.adapters.credential_projection import project_executor_credentials
from bora.plugins.middleware import NextFn

PLUGIN_ID = "default"
# Stronger than typical plugin 110 so this wrapper is outermost (cred → nxt → copy).
HOME_OVERLAY_PRIORITY = 10


def _as_path(raw: Any) -> Path | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return Path(text) if text else None


def copy_home_overlay_tree(overlay_root: Path, dest_home: Path) -> None:
    """Copy ``overlay_root/.`` into *dest_home* (merge; same-name overwrite)."""
    if not overlay_root.is_dir():
        return
    dest_home.mkdir(parents=True, exist_ok=True)
    for src in overlay_root.rglob("*"):
        rel = src.relative_to(overlay_root)
        dest = dest_home / rel
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def copy_allowlisted_auth_into_home(cred_root: Path, dest_home: Path) -> None:
    """Today's engine auth copies. Overlay tree is applied separately."""
    dest_home.mkdir(parents=True, exist_ok=True)
    pairs = (
        (cred_root / "codex_home" / "auth.json", dest_home / ".codex" / "auth.json"),
        (cred_root / "codex_home" / "config.toml", dest_home / ".codex" / "config.toml"),
        (cred_root / "codex_home" / "config.json", dest_home / ".codex" / "config.json"),
        (cred_root / "pi_home" / "agent" / "auth.json", dest_home / ".pi" / "agent" / "auth.json"),
        (
            cred_root / "opencode" / "auth.json",
            dest_home / ".local" / "share" / "opencode" / "auth.json",
        ),
        (cred_root / "grok_home" / "auth.json", dest_home / ".grok" / "auth.json"),
    )
    for src, dest in pairs:
        if not src.is_file():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


async def default_home_overlay(ctx: Any, value: Any, nxt: NextFn) -> Any:
    payload = dict(value) if isinstance(value, dict) else {}
    work_root = _as_path(payload.get("work_root"))
    if work_root is None and ctx is not None:
        work_root = _as_path(getattr(ctx, "work_root", None))
    if work_root is None:
        raise RuntimeError("home_overlay_missing_work_root")

    cred = project_executor_credentials(work_root=work_root)
    overlay_dir = cred.root / "home_overlay"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    payload["cred"] = cred
    payload["cred_root"] = cred.root
    if payload.get("package_root") is None:
        payload["package_root"] = getattr(ctx, "package_root", None)
    if payload.get("workspace_root") is None:
        payload["workspace_root"] = getattr(ctx, "workspace_root", None)
    if ctx is not None:
        ctx.cred = cred

    out = await nxt(payload)
    if isinstance(out, dict):
        payload = out

    docker = getattr(ctx, "docker", None) if ctx is not None else None
    if docker is not None:
        assert ctx is not None
        ledger = docker.prepare_agent_targets(
            ctx.runtime,
            ctx.topology,
            cred_root=cred.root,
            network_mode=getattr(ctx, "network_mode", None),
        )
        payload["ledger"] = ledger
        if ctx is not None:
            ctx.ledger = ledger
        return payload

    home_root = _as_path(payload.get("home_root")) or (work_root / "attempt-home")
    home_root.mkdir(parents=True, exist_ok=True)
    workspace_root = _as_path(payload.get("workspace_root"))
    if workspace_root is not None:
        workspace_root.mkdir(parents=True, exist_ok=True)
    copy_home_overlay_tree(overlay_dir, home_root)
    copy_allowlisted_auth_into_home(cred.root, home_root)
    payload["home_root"] = home_root
    if ctx is not None:
        ctx.home_root = home_root
    return payload
