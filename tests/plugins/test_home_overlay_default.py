"""Core default home_overlay preserves cred allowlist and wraps nxt."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from bora.plugins.defaults.home_overlay import (
    copy_home_overlay_tree,
    default_home_overlay,
)
from bora.plugins.slots import HOME_OVERLAY, SlotKind, get_slot_kind


def test_home_overlay_is_public_multi() -> None:
    assert get_slot_kind(HOME_OVERLAY) is SlotKind.MULTI


def test_default_creates_cred_then_calls_nxt_then_copies(tmp_path: Path) -> None:
    seen: list[str] = []

    async def plugin(value):  # type: ignore[no-untyped-def]
        seen.append("plugin")
        root = Path(value["cred_root"])
        dest = root / "home_overlay" / ".config" / "opencode" / "opencode.json"
        dest.parent.mkdir(parents=True)
        dest.write_text('{"provider":{}}\n', encoding="utf-8")
        assert (root / "home").is_dir()
        return value

    work = tmp_path / "work"
    work.mkdir()
    ctx = SimpleNamespace(work_root=work)
    out = asyncio.run(
        default_home_overlay(
            ctx,
            {"work_root": work, "package_root": tmp_path, "workspace_root": tmp_path / "ws"},
            plugin,
        )
    )
    assert seen == ["plugin"]
    home = Path(out["home_root"])
    assert (home / ".config" / "opencode" / "opencode.json").is_file()
    assert "home/" in ctx.cred.locator_keys


def test_overlay_tree_merges_and_overwrites(tmp_path: Path) -> None:
    src = tmp_path / "overlay"
    dest = tmp_path / "home"
    (src / "a").mkdir(parents=True)
    (src / "a" / "one.txt").write_text("new\n", encoding="utf-8")
    (dest / "a").mkdir(parents=True)
    (dest / "a" / "one.txt").write_text("old\n", encoding="utf-8")
    (dest / "a" / "keep.txt").write_text("stay\n", encoding="utf-8")
    copy_home_overlay_tree(src, dest)
    assert (dest / "a" / "one.txt").read_text(encoding="utf-8") == "new\n"
    assert (dest / "a" / "keep.txt").read_text(encoding="utf-8") == "stay\n"
