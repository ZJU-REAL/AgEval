"""Environment Manager — Attempt-local resource lifecycle (Spec 09)."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from bora.adapters.environment_postgres import PostgresEnvironment, new_postgres_environment


@dataclass
class EnvironmentManager:
    """Owns Attempt-scoped environment resources; no Benchmark/task branching."""

    attempt_id: str
    action_limit: int = 10
    _resources: dict[str, Any] = field(default_factory=dict)
    _actions: int = 0
    closed: bool = False

    def open_resource(self, kind: str, *, name: str | None = None) -> dict[str, Any]:
        if self.closed:
            return {"ok": False, "error": "environment_closed"}
        if kind != "postgresql":
            return {"ok": False, "error": "unknown_resource_kind", "kind": kind}
        env = (
            new_postgres_environment() if name is None else PostgresEnvironment(container_name=name)
        )
        env.action_limit = self.action_limit
        env.start(timeout=90.0)
        rid = f"{kind}:{env.container_name}"
        self._resources[rid] = env
        return {"ok": True, "resource_id": rid, "kind": kind}

    def action(
        self, resource_id: str, action_id: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self.closed:
            return {"ok": False, "error": "environment_closed"}
        if self._actions >= self.action_limit:
            return {"ok": False, "error": "environment_action_limit_exceeded"}
        env = self._resources.get(resource_id)
        if env is None:
            return {"ok": False, "error": "unknown_resource"}
        self._actions += 1
        return env.action(action_id, args)

    def freeze_snapshot(self, resource_id: str) -> dict[str, Any]:
        """Read-only snapshot of resource readiness (evaluator input strategy)."""
        if self.closed:
            return {"ok": False, "error": "environment_closed"}
        env = self._resources.get(resource_id)
        if env is None:
            return {"ok": False, "error": "unknown_resource"}
        return {
            "ok": True,
            "resource_id": resource_id,
            "ready": bool(getattr(env, "ready", False)),
            "actions": int(getattr(env, "actions", 0)),
            "kind": "postgresql",
        }

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for env in list(self._resources.values()):
            with contextlib.suppress(Exception):
                env.stop()
        self._resources.clear()
