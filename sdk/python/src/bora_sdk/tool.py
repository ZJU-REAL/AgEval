"""ToolSet — local tool dispatch with hooks and soft CallLimit.

Local soft policy only. Runtime Agent/Environment hard ceilings remain
parent-owned and independent of these guards.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

Observation = dict[str, Any]
ToolFn = Callable[[Mapping[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class AllowList:
    """Process-local tool name allow list (soft policy)."""

    names: frozenset[str]

    @classmethod
    def of(cls, *names: str) -> AllowList:
        return cls(names=frozenset(names))

    def allows(self, name: str) -> bool:
        return name in self.names


@dataclass(frozen=True, slots=True)
class CallLimit:
    """Process-local global call budget (soft policy; no Runtime quota authority)."""

    max_calls: int

    def __post_init__(self) -> None:
        if self.max_calls < 0:
            raise ValueError("max_calls must be >= 0")


@dataclass
class Tool:
    name: str
    fn: ToolFn
    schema: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ToolSet:
    tools: dict[str, Tool] = field(default_factory=dict)
    before_hooks: list[Callable[[str, Mapping[str, Any]], None]] = field(default_factory=list)
    after_hooks: list[Callable[[str, Observation], None]] = field(default_factory=list)
    allowlist: set[str] | AllowList | None = None
    call_limit: int | CallLimit | None = None
    _calls: int = 0
    _closed: bool = False
    side_effect_counter: int = 0  # for tests / deterministic packages

    def add(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def _allowed(self, name: str) -> bool:
        if self.allowlist is None:
            return True
        if isinstance(self.allowlist, AllowList):
            return self.allowlist.allows(name)
        return name in self.allowlist

    def _limit(self) -> int | None:
        if self.call_limit is None:
            return None
        if isinstance(self.call_limit, CallLimit):
            return self.call_limit.max_calls
        return int(self.call_limit)

    async def call(self, name: str, args: Mapping[str, Any] | None = None) -> Observation:
        if self._closed:
            return {"status": "denied", "reason": "closed"}
        args = dict(args or {})
        if not self._allowed(name):
            return {"status": "denied", "reason": "allowlist"}
        if name not in self.tools:
            return {"status": "denied", "reason": "unknown_tool"}
        limit = self._limit()
        if limit is not None and self._calls >= limit:
            return {"status": "denied", "reason": "call_limit"}
        tool = self.tools[name]
        # Schema check before before-hooks so invalid args never touch callable.
        required = tool.schema.get("required") if isinstance(tool.schema, Mapping) else None
        if isinstance(required, list):
            for key in required:
                if key not in args:
                    return {"status": "denied", "reason": "invalid_args"}
        for hook in self.before_hooks:
            hook(name, args)
        self._calls += 1
        result = tool.fn(args)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[misc]
        self.side_effect_counter += 1
        obs: Observation = {"status": "ok", "tool": name, "result": result}
        for hook in self.after_hooks:
            hook(name, obs)
        return obs

    def close(self) -> None:
        self._closed = True


def allowlist_from_params(names: Iterable[str]) -> AllowList:
    return AllowList.of(*list(names))
