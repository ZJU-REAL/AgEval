"""L0: observe env post_setup + one parent-bound agent invoke (slot-probe echo)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ageval_sdk import Agent, HarnessContext, HarnessTerminal


def _load_env_doc(package_dir: Path) -> dict:
    for cand in (
        package_dir / ".ageval_env_result.json",
        Path(os.environ.get("AGEVAL_WORKSPACE_ROOT") or ".") / ".ageval_env_result.json",
    ):
        if cand.is_file():
            return json.loads(cand.read_text(encoding="utf-8"))
    return {}


async def run(ctx: HarnessContext) -> HarnessTerminal:
    package_dir = Path(__file__).resolve().parent
    env_doc = _load_env_doc(package_dir)
    post_setup = env_doc.get("post_setup") if isinstance(env_doc, dict) else None
    marker = package_dir / "post_setup.ok"
    post_setup_file = marker.is_file()
    if post_setup_file:
        marker_text = marker.read_text(encoding="utf-8").strip()
    else:
        marker_text = ""

    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("probe-nooa", max_turns=1) as session:
        inv = await session.invoke(
            'Return ONLY JSON {"answer": 42} with no other keys.'
        )

    if not inv.get("ok"):
        return HarnessTerminal.failed(inv.get("error") or "invoke_failed")

    structured = inv.get("structured") if isinstance(inv.get("structured"), dict) else {}
    answer = structured.get("answer")
    text = str(inv.get("text") or "")

    report = {
        "task": "l0-env-agent",
        "assurance": "l0",
        "post_setup_file": post_setup_file,
        "post_setup_text": marker_text,
        "post_setup_handoff": post_setup,
        "slot_probe_inject": bool(env_doc.get("slot_probe_inject")) if env_doc else False,
        "invoke_ok": True,
        "answer": answer,
        "text_has_slot_probe_tag_expected_in_trajectory": True,
        "text_preview": text[:200],
    }
    ctx.publish_json("probe-report", report)

    if not post_setup_file and not (
        isinstance(post_setup, dict) and post_setup.get("ok")
    ):
        return HarnessTerminal.failed("env_post_setup_not_observed")
    if answer != 42:
        return HarnessTerminal.failed(f"unexpected_answer:{answer}")
    return HarnessTerminal.completed("l0-env-agent")
