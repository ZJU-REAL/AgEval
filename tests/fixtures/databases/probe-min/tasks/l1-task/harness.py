from __future__ import annotations

from pathlib import Path


async def run(ctx):  # type: ignore[no-untyped-def]
    out = Path(ctx.workspace_root) / "artifacts"
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text('{"ok": true}\n', encoding="utf-8")
    return {"kind": "completed", "ok": True}
