"""Thin task entry — orchestration in Dataset shared/lib (#65)."""
from __future__ import annotations
from pathlib import Path
from bora_sdk import HarnessContext, HarnessTerminal
from shared.lib.harness_core import run as _run
_TASK = Path(__file__).resolve().parent
UPSTREAM_TASK_ID = "1"
async def run(ctx: HarnessContext) -> HarnessTerminal:
    view = ctx.params
    if hasattr(view, "as_mapping"):
        data = dict(view.as_mapping())
        if not data.get("upstream_task_id"):
            data["upstream_task_id"] = UPSTREAM_TASK_ID
            class _P:
                def as_mapping(self):
                    return data
                def get(self, path, default=None):
                    cur = data
                    for part in str(path).split("."):
                        if not isinstance(cur, dict) or part not in cur:
                            return default
                        cur = cur[part]
                    return cur
            ctx.params = _P()  # type: ignore[misc]
    return await _run(ctx, task_dir=_TASK)
