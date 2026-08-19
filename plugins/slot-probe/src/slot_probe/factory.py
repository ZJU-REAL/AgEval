"""Provide factories: deterministic executor + evaluation_runtime marker."""

from __future__ import annotations

import json
import re
from typing import Any

from ageval.plugins.agent_result import AgentResult

from slot_probe.audit import audit

PLUGIN_ID = "slot-probe"
_ANSWER_RE = re.compile(r'"answer"\s*:\s*(\d+)')


class SlotProbeEchoExecutor:
    """Host-only echo SPI: parse answer from prompt or default 42."""

    kind = "slot-probe"

    def __init__(self, **kwargs: Any) -> None:
        self.model = str(kwargs.get("model") or "slot-probe-echo")
        self.profile_id = kwargs.get("profile_id")

    def open(self, **kwargs: Any) -> None:
        del kwargs
        audit("executor.open", profile_id=self.profile_id)

    def close(self) -> None:
        audit("executor.close", profile_id=self.profile_id)

    def invoke(self, prompt: str, **kwargs: Any) -> AgentResult:
        del kwargs
        m = _ANSWER_RE.search(prompt or "")
        answer = int(m.group(1)) if m else 42
        structured = {"answer": answer, "plugin": PLUGIN_ID}
        text = json.dumps(structured, sort_keys=True)
        audit("executor.invoke", prompt_len=len(prompt or ""), answer=answer)
        return AgentResult(
            model=self.model,
            text=text,
            structured=structured,
            ok=True,
            metadata={"executor_kind": PLUGIN_ID, "plugin": PLUGIN_ID},
        )


def build_executor(**kwargs: Any) -> SlotProbeEchoExecutor:
    return SlotProbeEchoExecutor(**kwargs)


def build_evaluation_runtime(**kwargs: Any) -> dict[str, Any]:
    del kwargs
    audit("evaluation_runtime")
    return {"runtime": "package", "source": "slot-probe", "plugin": PLUGIN_ID}
