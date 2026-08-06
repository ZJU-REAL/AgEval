"""Minimal harness for registry fixture."""

from __future__ import annotations

from pathlib import Path


async def run(ctx):  # type: ignore[no-untyped-def]
    out = Path(ctx.workspace_root) / "artifacts"
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text('{"ok": true, "task": "hello"}\n', encoding="utf-8")
    # Return completed terminal if SDK types available; else plain dict envelope.
    try:
        from bora_sdk import HarnessTerminal

        ctx.publish_json("result", {"ok": True, "task": "hello"})
        return HarnessTerminal.completed()
    except Exception:  # noqa: BLE001
        return {"kind": "completed", "ok": True}
