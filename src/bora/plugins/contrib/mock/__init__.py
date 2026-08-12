"""mock first-party executor: offline fixture / config lock smoke only."""

from __future__ import annotations

from typing import Any

from bora.adapters.agent_contract import AgentResult
from bora.plugins.protocol import ExecutorSPI
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.slots import EXECUTOR

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
        del options, profile_id, base_url, api_key, plugin_id
        self.model = model or "none"

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
