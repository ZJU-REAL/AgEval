"""Task-local typed agent — package owns this; nooa plugin only invokes it."""

from __future__ import annotations

from typing import Any


class FixedAnswerAgent:
    """Deterministic agent for Phase A nooa host e2e (no LLM)."""

    def run(self, prompt: str, workdir: str | None = None) -> dict[str, Any]:
        del prompt, workdir
        return {
            "ok": True,
            "text": '{"answer": 42}',
            "structured": {"answer": 42, "source": "FixedAnswerAgent"},
        }
