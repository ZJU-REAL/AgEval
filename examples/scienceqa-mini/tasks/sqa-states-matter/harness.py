"""ScienceQA-mini harness: one MCQ invoke, publish parsed letter."""

from __future__ import annotations

import re

from ageval_sdk import Agent, RunContext, RunTerminal

LETTER_RE = re.compile(r"\b([ABCD])\b")


async def run(ctx: RunContext) -> RunTerminal:
    question = ctx.params.require_str("question")
    opts = ctx.params.get("options") or {}
    lines = [f"{k}. {opts[k]}" for k in sorted(opts)]
    prompt = (
        "You are answering a multiple-choice science question.\n\n"
        f"Question: {question}\n" + "\n".join(lines)
        + "\n\nReply with ONLY the single letter (A, B, C or D) of the correct option."
    )
    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("solver", max_turns=2) as session:
        resp = await session.invoke(prompt)
    if not resp.get("ok"):
        return RunTerminal.failed(str(resp.get("error") or "invoke_failed"))
    text = str(resp.get("text") or "")
    match = LETTER_RE.search(text.strip().upper())
    ctx.publish_json("answer", {"raw": text, "letter": match.group(1) if match else None})
    return RunTerminal.completed("scienceqa-mini")
