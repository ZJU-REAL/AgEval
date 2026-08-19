"""Test helpers: an AgentBinder bound to a scripted executor.

The executor is a stand-in for a real Agent backend so unit tests can exercise
the parent service's own rules (ceilings, deadlines, sealing). Nothing here is
evidence that an Agent path works — that is what the public smoke is for.
"""

from __future__ import annotations

from typing import Any

from ageval.plugins.agent_result import AgentResult
from ageval.plugins.protocol import ExtensionGraph, WinnerRef
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.services import ServiceTable
from ageval.plugins.slots import EXECUTOR
from ageval.runtime.agent_binding import AgentBinder, BoundAgent


class ScriptedExecutor:
    """Replies with the answer index of the call, or raises / stalls on demand."""

    kind = "scripted"

    def __init__(self, *, raises: BaseException | None = None, ok: bool = True) -> None:
        self.prompts: list[str] = []
        self.timeouts: list[float] = []
        self.closed = False
        self._raises = raises
        self._ok = ok

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        collect_dir: Any = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del collect_dir, redaction_sentinels
        self.prompts.append(prompt)
        self.timeouts.append(timeout)
        if self._raises is not None:
            raise self._raises
        turn = len(self.prompts)
        return AgentResult(
            model="scripted-model",
            text=f'{{"answer": {40 + turn}}}',
            structured={"answer": 40 + turn, "turn": turn},
            ok=self._ok,
            error=None if self._ok else "scripted_failure",
            metadata={"executor_kind": self.kind},
        )

    def close(self) -> None:
        self.closed = True


class ScriptedBinder(AgentBinder):
    """Binds one declared profile id to a fixed executor instance."""

    def __init__(self, executor: Any, *, profile_id: str = "solver") -> None:
        super().__init__(
            profiles=({"id": profile_id, "executor": ScriptedExecutor.kind},),
            services=ServiceTable(),
            registry=ExtensionRegistry(),
        )
        self._executor = executor
        self.bind_calls = 0

    def bind(self, profile_id: str) -> BoundAgent:
        row = self.profile(profile_id)
        self.bind_calls += 1
        graph = ExtensionGraph(profile_id=profile_id)
        graph.winners[EXECUTOR] = WinnerRef(
            plugin_id=ScriptedExecutor.kind,
            impl=type(self._executor),
            priority=10,
            source="test",
            slot=EXECUTOR,
        )
        return BoundAgent(
            profile_id=profile_id,
            plugin_id=ScriptedExecutor.kind,
            executor=self._executor,
            graph=graph,
            model=str(row.get("model") or "scripted-model"),
        )
