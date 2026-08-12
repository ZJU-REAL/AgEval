from __future__ import annotations

from typing import Any

from bora.adapters.agent_contract import AgentResult


class EchoExecutor:
    kind = "sample-echo"

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def open(self, **kwargs: Any) -> None:
        del kwargs

    def close(self) -> None:
        return None

    def invoke(self, prompt: str, **kwargs: Any) -> AgentResult:
        del kwargs
        return AgentResult(model="echo", text=prompt, structured={"echo": prompt}, ok=True)


def build_executor(**kwargs: Any) -> EchoExecutor:
    return EchoExecutor(**kwargs)
