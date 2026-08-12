"""Task-local typed agent — package owns this; nooa plugin only invokes it."""

from __future__ import annotations

from typing import Any


class FixedAnswerAgent:
    """Deterministic agent for L0 slot-probe e2e (no LLM)."""

    def run(self, prompt: str, workdir: str | None = None) -> dict[str, Any]:
        del workdir
        # Observe slot-probe before_agent_invoke tag in prompt when present.
        tagged = "[slot-probe]" in (prompt or "")
        return {
            "ok": True,
            "text": '{"answer": 42}',
            "structured": {
                "answer": 42,
                "source": "FixedAnswerAgent",
                "saw_slot_probe_tag": tagged,
            },
        }
