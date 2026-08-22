"""AgentSession / Agent thin facade (HC-2).

Logical Attempt-bound session only. Provider continuation remains unsupported.
Real invokes go to parent Agent Service via Unix socket when bound.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


def _parent_call(payload: dict[str, Any]) -> dict[str, Any]:
    """Length-prefixed JSON over Unix socket to parent Agent Service."""
    import json
    import socket
    import struct

    sock_path = os.environ.get("AGEVAL_AGENT_SERVICE_SOCK")
    if not sock_path:
        return {"ok": False, "error": "agent_session_unbound"}
    if os.environ.get("AGEVAL_OFFLINE_AGENT") == "1" and payload.get("op") == "invoke":
        return {"ok": False, "error": "offline_forced", "structured": None}
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.connect(sock_path)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        conn.sendall(struct.pack("!I", len(raw)) + raw)
        hdr = conn.recv(4)
        if len(hdr) < 4:
            return {"ok": False, "error": "agent_service_eof"}
        (n,) = struct.unpack("!I", hdr)
        body = b""
        while len(body) < n:
            chunk = conn.recv(n - len(body))
            if not chunk:
                return {"ok": False, "error": "agent_service_eof"}
            body += chunk
        return json.loads(body.decode("utf-8"))
    except OSError as exc:
        return {"ok": False, "error": f"agent_service_connect:{type(exc).__name__}"}
    finally:
        conn.close()


@dataclass
class AgentSession:
    """Attempt-bound logical session (no provider resume token)."""

    attempt_id: str
    profile_id: str
    max_turns: int = 8
    actor_id: str | None = None
    _turns: int = 0
    _closed: bool = False
    provider_session_handle: None = None  # always null/unsupported for Codex
    _session_id: str | None = field(default=None, repr=False)
    _last_invocation_id: str | None = field(default=None, repr=False)

    def _ensure_open(self) -> Mapping[str, Any]:
        if self._session_id is not None:
            return {"ok": True, "session_id": self._session_id}
        payload: dict[str, Any] = {
            "op": "open",
            "attempt_id": self.attempt_id,
            "profile_id": self.profile_id,
        }
        if self.actor_id is not None:
            payload["actor_id"] = self.actor_id
        resp = _parent_call(payload)
        if not resp.get("ok"):
            return resp
        self._session_id = str(resp.get("session_id") or "")
        return resp

    async def invoke(self, prompt: str, **kwargs: Any) -> Mapping[str, Any]:
        if self._closed:
            raise RuntimeError("session closed")
        tools = kwargs.pop("tools", None)
        messages = kwargs.pop("messages", None)
        if kwargs:
            # Disallow profile/workspace/executor overrides mid-session.
            raise ValueError("session invoke does not accept profile overrides")
        if self._turns >= self.max_turns:
            raise RuntimeError("local max_turns exceeded")
        self._turns += 1

        if os.environ.get("AGEVAL_OFFLINE_AGENT") == "1":
            return {
                "text": "",
                "structured": None,
                "provider_session_handle": None,
                "turn": self._turns,
                "ok": False,
                "error": "offline_forced",
                "tool_calls": [],
            }

        opened = self._ensure_open()
        if not opened.get("ok"):
            return {
                "text": "",
                "structured": None,
                "provider_session_handle": None,
                "turn": self._turns,
                "ok": False,
                "error": opened.get("error") or "agent_session_unbound",
                "tool_calls": [],
            }

        payload: dict[str, Any] = {
            "op": "invoke",
            "session_id": self._session_id,
            "attempt_id": self.attempt_id,
            "prompt": prompt,
        }
        if tools is not None:
            payload["tools"] = tools
        if messages is not None:
            payload["messages"] = messages
        resp = _parent_call(payload)
        inv = resp.get("invocation_id")
        if isinstance(inv, str) and inv:
            self._last_invocation_id = inv
        return {
            "text": resp.get("text") or "",
            "structured": resp.get("structured"),
            "provider_session_handle": None,
            "turn": self._turns,
            "ok": bool(resp.get("ok")),
            "error": resp.get("error"),
            "invocation_id": resp.get("invocation_id"),
            "evidence_relative": resp.get("evidence_relative"),
            "tool_calls": list(resp.get("tool_calls") or []),
        }

    async def record_observation(
        self,
        tool_call_id: str,
        *,
        content: str,
        raw_output: Any = None,
        function_name: str | None = None,
        error: bool = False,
        invocation_id: str | None = None,
    ) -> Mapping[str, Any]:
        """Supplement the last invoke with a domain-tool observation.

        Parent does not execute package tools. Call this after ToolSet.call /
        Environment.get_response. Not PASS. Does not consume invoke quota.
        """
        if self._closed:
            raise RuntimeError("session closed")
        if os.environ.get("AGEVAL_OFFLINE_AGENT") == "1":
            return {"ok": False, "error": "offline_forced"}
        if not self._session_id:
            return {"ok": False, "error": "agent_session_unbound"}
        payload: dict[str, Any] = {
            "op": "record_observation",
            "session_id": self._session_id,
            "tool_call_id": tool_call_id,
            "content": content,
            "error": bool(error),
        }
        inv = invocation_id or self._last_invocation_id
        if inv:
            payload["invocation_id"] = inv
        if function_name:
            payload["function_name"] = function_name
        if raw_output is not None:
            payload["raw_output"] = raw_output
        return _parent_call(payload)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._session_id:
            _parent_call({"op": "close", "session_id": self._session_id})

    async def __aenter__(self) -> AgentSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()


@dataclass
class Agent:
    """Thin facade that opens Attempt-bound sessions from context scope."""

    attempt_id: str

    def session(
        self,
        profile_id: str,
        *,
        max_turns: int = 8,
        actor_id: str | None = None,
    ) -> AgentSession:
        """Open a logical session.

        L1 packages must pass ``actor_id`` (isolation principal). L0 may omit it.
        """
        return AgentSession(
            attempt_id=self.attempt_id,
            profile_id=profile_id,
            max_turns=max_turns,
            actor_id=actor_id,
        )
