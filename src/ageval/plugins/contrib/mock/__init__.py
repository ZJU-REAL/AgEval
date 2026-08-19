"""mock first-party executor: offline fixture / config lock smoke only."""

from __future__ import annotations

from typing import Any

from ageval.adapters.agent_contract import AgentResult
from ageval.plugins.protocol import ExecutorSPI
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import EXECUTOR
from ageval.runtime.offline import is_offline_agent

PLUGIN_ID = "mock"
PRIORITY = 900  # weak; only selected via profiles executor: mock


class MockExecutorSPI(ExecutorSPI):
    kind = "mock"

    def __init__(
        self,
        *,
        options: dict[str, Any] | None = None,
        profile_id: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        plugin_id: str | None = None,
        **_kwargs: Any,
    ) -> None:
        del profile_id, base_url, api_key, plugin_id
        self.model = model or "none"
        self._options = dict(options or {})

    def open(self, **kwargs: Any) -> None:
        del kwargs

    def close(self) -> None:
        return None

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del timeout, workdir, collect_dir, redaction_sentinels
        # Injectable only under offline gate — never a silent production success path.
        fixture = self._options.get("offline_fixture")
        if is_offline_agent() and isinstance(fixture, dict):
            return AgentResult(
                model=self.model,
                text=str(fixture.get("text") or ""),
                structured=fixture.get("structured"),
                ok=bool(fixture.get("ok", True)),
                error=str(fixture["error"]) if fixture.get("error") else None,
                metadata={"plugin": PLUGIN_ID, "prompt_len": len(prompt), "fixture": True},
            )
        return AgentResult(
            model=self.model,
            text="",
            structured=None,
            ok=False,
            error="mock_executor_not_for_production",
            metadata={"plugin": PLUGIN_ID, "prompt_len": len(prompt)},
        )


def _factory(**kwargs: Any) -> MockExecutorSPI:
    return MockExecutorSPI(**kwargs)


def register_mock_contrib(registry: ExtensionRegistry) -> None:
    registry.provide(
        EXECUTOR,
        PLUGIN_ID,
        _factory,
        priority=PRIORITY,
        source="first-party",
        is_factory=True,
    )


__all__ = ["PLUGIN_ID", "MockExecutorSPI", "register_mock_contrib"]
