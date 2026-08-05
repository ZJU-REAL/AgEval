from __future__ import annotations
import asyncio
import json
from pathlib import Path

async def run(ctx):
    params = dict(ctx.params) if hasattr(ctx, "params") else {}
    try:
        sleep_ms = int(params.get("sleep_ms") or 0)
    except Exception:
        sleep_ms = 0
    if sleep_ms:
        await asyncio.sleep(sleep_ms / 1000.0)
    expect = params.get("expect_pass", True)
    # YAML may load true as bool
    out_dir = Path(ctx.workspace_root) / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"ok": bool(expect) if not isinstance(expect, str) else expect.lower() == "true", "task": "x"}
    (out_dir / "result.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    try:
        from bora_sdk import HarnessTerminal
        ctx.publish_json("result", payload)
        return HarnessTerminal.completed()
    except Exception:
        return {"kind": "completed", "ok": True}
