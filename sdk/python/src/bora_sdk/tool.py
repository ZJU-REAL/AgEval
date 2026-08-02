"""ToolSet — local tool dispatch with hooks and soft CallLimit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

Observation = dict[str, Any]
ToolFn = Callable[[Mapping[str, Any]], Any | Awaitable[Any]]


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
    allowlist: set[str] | None = None
    call_limit: int | None = None
    _calls: int = 0
    _closed: bool = False
    side_effect_counter: int = 0  # for tests / deterministic packages

    def add(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    async def call(self, name: str, args: Mapping[str, Any] | None = None) -> Observation:
        if self._closed:
            return {"status": "denied", "reason": "closed"}
        args = dict(args or {})
        if self.allowlist is not None and name not in self.allowlist:
            return {"status": "denied", "reason": "allowlist"}
        if name not in self.tools:
            return {"status": "denied", "reason": "unknown_tool"}
        if self.call_limit is not None and self._calls >= self.call_limit:
            return {"status": "denied", "reason": "call_limit"}
        for hook in self.before_hooks:
            hook(name, args)
        tool = self.tools[name]
        # Minimal schema: required keys if provided.
        required = tool.schema.get("required") if isinstance(tool.schema, Mapping) else None
        if isinstance(required, list):
            for key in required:
                if key not in args:
                    return {"status": "denied", "reason": "invalid_args"}
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
