"""Write a workspace tree. Runtime harvests it; this is not PASS."""

from __future__ import annotations

from ageval_sdk import RunContext, RunTerminal


async def run(ctx: RunContext) -> RunTerminal:
    (ctx.workspace_root / "answer.txt").write_text("42\n", encoding="utf-8")
    leaked = ctx.workspace_root / "target"
    leaked.mkdir(exist_ok=True)
    (leaked / "leak.so").write_bytes(b"build-product")
    ctx.publish_tree("repo", ctx.workspace_root)
    return RunTerminal.completed("ok")
