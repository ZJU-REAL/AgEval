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
    # Optional Attempt evidence sink for effects.jsonl (Spec 15 / §8.9).
    evidence_store: Any | None = None
    # Optional #71 C env_action provide SPI: object with check(resource_id, action_id, args).
    action_gate: Any | None = None
    _resources: dict[str, Any] = field(default_factory=dict)
    _actions: int = 0
    closed: bool = False

    def _effect(self, decision: dict[str, Any]) -> None:
        if self.evidence_store is None:
            return
        with contextlib.suppress(Exception):
            self.evidence_store.append_effect(
                {
                    "owner": "environment_manager",
                    "attempt_id": self.attempt_id,
                    **decision,
                }
            )

    def open_resource(self, kind: str, *, name: str | None = None) -> dict[str, Any]:
        if self.closed:
            self._effect({"decision": "deny", "reason": "environment_closed", "op": "open"})
            return {"ok": False, "error": "environment_closed"}
        if kind != "postgresql":
            self._effect(
                {
                    "decision": "deny",
                    "reason": "unknown_resource_kind",
                    "op": "open",
                    "kind": kind,
                }
            )
            return {"ok": False, "error": "unknown_resource_kind", "kind": kind}
        env = (
            new_postgres_environment() if name is None else PostgresEnvironment(container_name=name)
        )
        env.action_limit = self.action_limit
        env.start(timeout=90.0)
        rid = f"{kind}:{env.container_name}"
        self._resources[rid] = env
        self._effect({"decision": "allow", "op": "open", "kind": kind, "resource_id": rid})
        return {"ok": True, "resource_id": rid, "kind": kind}

    def action(
        self, resource_id: str, action_id: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self.closed:
            self._effect({"decision": "deny", "reason": "environment_closed", "op": action_id})
            return {"ok": False, "error": "environment_closed"}
        if self._actions >= self.action_limit:
            self._effect(
                {
                    "decision": "deny",
                    "reason": "environment_action_limit_exceeded",
                    "op": action_id,
                }
            )
            return {"ok": False, "error": "environment_action_limit_exceeded"}
        env = self._resources.get(resource_id)
        if env is None:
            self._effect(
                {
                    "decision": "deny",
                    "reason": "unknown_resource",
                    "op": action_id,
                    "resource_id": resource_id,
                }
            )
            return {"ok": False, "error": "unknown_resource"}
        # #71 C: env_action provide SPI may deny before resource effect.
        if self.action_gate is not None and hasattr(self.action_gate, "check"):
            try:
                gate = self.action_gate.check(resource_id, action_id, args or {})
            except Exception as exc:  # noqa: BLE001 — fail closed on gate errors
                self._effect(
                    {
                        "decision": "deny",
                        "reason": "env_action_gate_error",
                        "op": action_id,
                        "error": type(exc).__name__,
                    }
                )
                return {"ok": False, "error": f"env_action_gate_error:{type(exc).__name__}"}
            if isinstance(gate, dict) and gate.get("ok") is False:
                self._effect(
                    {
                        "decision": "deny",
                        "reason": "env_action_denied",
                        "op": action_id,
                        "resource_id": resource_id,
                        "error": gate.get("error"),
                    }
                )
                return gate
        self._actions += 1
        result = env.action(action_id, args)
        self._effect(
            {
                "decision": "allow" if result.get("ok") else "deny",
                "op": action_id,
                "resource_id": resource_id,
                "ok": bool(result.get("ok")),
                "error": result.get("error"),
            }
        )
        return result

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
