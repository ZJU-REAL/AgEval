"""Single typed ACP executor (Spec 19).

Parent/host only: spawns (or attaches to) an ACP entry process over stdio via
``agent-client-protocol``. Vendor private stdout scrape is forbidden.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress as contextlib_suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bora import __version__ as BORA_VERSION
from bora.adapters.acp_registry import AcpEntryDescriptor, get_entry, readiness_for
from bora.adapters.agent_contract import AgentResult, parse_validated_text_structured

# Optional process launcher: (command, args, env, cwd) -> provides streams.
# Host default uses acp.spawn_agent_process. L1 injects docker-exec launcher.
ProcessLauncher = Callable[..., Any]


def write_trajectory_jsonl(
    inv_dir: Path,
    *,
    prompt: str,
    events: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    final_text: str,
    structured: dict[str, object] | None,
    usage: dict[str, Any] | None,
    ok: bool,
    error: str | None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Write **turn-level** training trajectory for one BORA invoke.

    One ``session/prompt`` (one invoke) → one training turn unit:

    1. ``user`` — full prompt
    2. ``assistant`` (optional ``part=thought``) — merged thought text
    3. ``assistant`` — merged message text (prefer ``final_text``)
    4. ``terminal`` — ok / error / structured / usage / stop metadata

    Stream chunks are merged; raw token-level ACP updates are not written here.
    Optional debug stream stays out of this file (see ``events.jsonl`` if needed).
    Not PASS authority.
    """
    inv_dir.mkdir(parents=True, exist_ok=True)
    path = inv_dir / "trajectory.jsonl"

    thought_parts: list[str] = []
    assistant_parts: list[str] = []
    permission_events: list[dict[str, Any]] = []
    acp_session_id: str | None = None

    for ev in events:
        if not isinstance(ev, dict):
            continue
        sid = ev.get("session_id")
        if isinstance(sid, str) and sid:
            acp_session_id = sid
        if ev.get("type") == "permission_decision":
            permission_events.append(
                {
                    "type": "permission_decision",
                    "outcome": ev.get("outcome"),
                    "option_id": ev.get("option_id"),
                    "policy": ev.get("policy"),
                    "source": "acp",
                }
            )
            continue
        channel = ev.get("channel")
        text = ev.get("text")
        if not isinstance(text, str):
            continue
        if channel == "thought":
            thought_parts.append(text)
        elif channel == "assistant":
            assistant_parts.append(text)

    merged_thought = "".join(thought_parts)
    merged_assistant = final_text if final_text else "".join(assistant_parts)

    turn_index = 1
    if isinstance(metadata, dict):
        # Optional: callers may pass bora turn index later.
        raw_ti = metadata.get("turn_index")
        if isinstance(raw_ti, int) and raw_ti > 0:
            turn_index = raw_ti

    lines: list[dict[str, Any]] = [
        {
            "type": "turn",
            "role": "user",
            "content": prompt,
            "turn_index": turn_index,
            "acp_session_id": acp_session_id,
            "source": "bora",
        }
    ]
    if merged_thought:
        lines.append(
            {
                "type": "turn",
                "role": "assistant",
                "part": "thought",
                "content": merged_thought,
                "turn_index": turn_index,
                "acp_session_id": acp_session_id,
                "source": "acp",
            }
        )
    lines.append(
        {
            "type": "turn",
            "role": "assistant",
            "content": merged_assistant,
            "turn_index": turn_index,
            "acp_session_id": acp_session_id,
            "source": "acp",
        }
    )
    for pe in permission_events:
        pe = {**pe, "turn_index": turn_index, "acp_session_id": acp_session_id}
        lines.append(pe)
    lines.append(
        {
            "type": "terminal",
            "ok": ok,
            "error": error,
            "turn_index": turn_index,
            "acp_session_id": acp_session_id,
            "structured": structured,
            "usage": usage,
            "stop_reason": (metadata or {}).get("stop_reason") if metadata else None,
            "metadata": {
                k: (metadata or {}).get(k)
                for k in (
                    "executor_kind",
                    "acp_entry_id",
                    "acp_version",
                    "protocol_version",
                    "actual_model",
                    "locked_model",
                )
                if metadata and k in metadata
            },
            "source": "bora",
        }
    )
    path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in lines) + "\n",
        encoding="utf-8",
    )
    return path


def _offline_result(model: str) -> AgentResult:
    return AgentResult(
        model=model,
        text="",
        structured=None,
        ok=False,
        error="offline_forced",
        events=(
            {
                "type": "lifecycle",
                "phase": "skipped",
                "reason": "offline_forced",
                "source": "acp_adapter",
            },
        ),
        metadata={"executor_kind": "acp"},
    )


def _auto_approve_permission(options: Sequence[Any]) -> Any:
    """Batch auto-approve: select first allow-like option (Spec 19 decision 4)."""
    import acp
    from acp.schema import AllowedOutcome

    option_id = None
    for opt in options:
        kind = getattr(opt, "kind", None) or (opt.get("kind") if isinstance(opt, dict) else None)
        oid = getattr(opt, "option_id", None) or (
            opt.get("optionId") if isinstance(opt, dict) else None
        )
        if kind in ("allow_once", "allow_always", "allow", "selected") or (
            isinstance(oid, str) and "allow" in oid.lower()
        ):
            option_id = oid
            break
    if option_id is None and options:
        first = options[0]
        option_id = getattr(first, "option_id", None) or (
            first.get("optionId") if isinstance(first, dict) else None
        )
    if not option_id:
        option_id = "allow"
    return acp.RequestPermissionResponse(
        outcome=AllowedOutcome(optionId=str(option_id), outcome="selected")
    )


@dataclass
class _BoraAcpClient:
    """Minimal Client: auto-approve permission, decline elicitation, collect updates."""

    events: list[dict[str, Any]] = field(default_factory=list)
    text_chunks: list[str] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    permission_decisions: list[dict[str, Any]] = field(default_factory=list)
    _conn: Any = None

    def on_connect(self, conn: Any) -> None:
        self._conn = conn

    async def request_permission(
        self,
        session_id: str,
        tool_call: Any,
        options: list[Any],
        **kwargs: Any,
    ) -> Any:
        resp = _auto_approve_permission(options)
        decision = {
            "type": "permission_decision",
            "session_id": session_id,
            "outcome": "selected",
            "policy": "batch_auto_approve",
            "source": "acp_client",
        }
        # Record option id without tool payloads that may carry paths/secrets.
        try:
            decision["option_id"] = resp.outcome.option_id  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            decision["option_id"] = "allow"
        self.permission_decisions.append(decision)
        self.events.append(decision)
        return resp

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        """Record full ACP stream for trajectory.jsonl (training-grade).

        Intermediate AgentMessageChunk / thought text is preserved on the event
        payload (not only text_len). Operators who run local smokes want the
        raw stream for post-hoc training export.
        """
        update_type = type(update).__name__
        event: dict[str, Any] = {
            "type": "session_update",
            "session_id": session_id,
            "update_type": update_type,
            "source": "acp",
        }
        # Prefer typed dump when available (full structured update).
        with contextlib_suppress(Exception):
            if hasattr(update, "model_dump"):
                dumped = update.model_dump(by_alias=True, exclude_none=True)
                if isinstance(dumped, dict):
                    event["update"] = dumped

        content = getattr(update, "content", None)
        text = getattr(content, "text", None) if content is not None else None
        is_agent_msg = "AgentMessage" in update_type or update_type.endswith(
            "AgentMessageChunk"
        )
        is_thought = "Thought" in update_type or update_type.endswith("AgentThoughtChunk")
        if isinstance(text, str):
            event["text"] = text
            event["text_len"] = len(text)
            if is_agent_msg:
                self.text_chunks.append(text)
            if is_thought:
                event["channel"] = "thought"
            elif is_agent_msg:
                event["channel"] = "assistant"
        # Tool call updates: keep id/title/kind when present.
        for attr in ("tool_call_id", "toolCallId", "title", "kind", "status"):
            val = getattr(update, attr, None)
            if val is not None and attr not in event:
                # normalize camelCase keys already in model_dump; keep flat helpers
                key = "tool_call_id" if attr in {"tool_call_id", "toolCallId"} else attr
                event[key] = val if not hasattr(val, "value") else str(val)
        # UsageUpdate
        if "Usage" in update_type:
            usage_obj = getattr(update, "usage", None) or update
            with contextlib_suppress(Exception):
                if hasattr(usage_obj, "model_dump"):
                    self.usage = usage_obj.model_dump(by_alias=True, exclude_none=True)
                elif isinstance(usage_obj, dict):
                    self.usage = usage_obj
            if self.usage is not None:
                event["usage"] = self.usage
            event["has_usage"] = True
        self.events.append(event)

    async def write_text_file(
        self, session_id: str, path: str, content: str, **kwargs: Any
    ) -> None:
        # Not advertised; if called, refuse — tools run in entry process.
        raise RuntimeError("acp_client_fs_proxy_disabled")

    async def read_text_file(
        self,
        session_id: str,
        path: str,
        line: int | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> Any:
        raise RuntimeError("acp_client_fs_proxy_disabled")

    async def create_terminal(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("acp_client_terminal_proxy_disabled")

    async def terminal_output(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("acp_client_terminal_proxy_disabled")

    async def release_terminal(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def wait_for_terminal_exit(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("acp_client_terminal_proxy_disabled")

    async def kill_terminal(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def create_elicitation(self, message: str, mode: Any, **kwargs: Any) -> Any:
        import acp

        self.events.append(
            {
                "type": "elicitation",
                "action": "decline",
                "policy": "batch_decline",
                "source": "acp_client",
            }
        )
        return acp.DeclineElicitationResponse(action="decline")

    async def complete_elicitation(self, elicitation_id: str, **kwargs: Any) -> None:
        return None

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None


def _map_stop_reason(stop: str | None) -> tuple[bool, str | None]:
    if stop is None or stop in ("end_turn", "end-turn", "stop"):
        return True, None
    mapping = {
        "max_tokens": "acp_stop_max_tokens",
        "max_turn_requests": "acp_stop_max_turn_requests",
        "refusal": "acp_stop_refusal",
        "cancelled": "acp_cancelled",
        "canceled": "acp_cancelled",
    }
    err = mapping.get(str(stop), f"acp_stop_{stop}")
    return False, err


class AcpExecutor:
    """Descriptor-driven ACP executor; one process/session per BORA session reuse."""

    kind: str = "acp"

    def __init__(
        self,
        *,
        entry_id: str,
        model: str = "entry-default",
        base_url: str | None = None,
        api_key_env: str | None = None,
        descriptor: AcpEntryDescriptor | None = None,
        workdir: str | None = None,
        env: Mapping[str, str] | None = None,
        process_launcher: ProcessLauncher | None = None,
        command_override: Sequence[str] | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.model = model
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.descriptor = descriptor or get_entry(entry_id)
        if self.descriptor is None:
            raise KeyError(f"unknown_acp_entry:{entry_id}")
        self.workdir = workdir
        self._extra_env = dict(env or {})
        self._process_launcher = process_launcher
        self._command_override = list(command_override) if command_override else None

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._conn: Any = None
        self._process: Any = None
        self._client: _BoraAcpClient | None = None
        self._acp_session_id: str | None = None
        self._agent_info: dict[str, Any] | None = None
        self._protocol_version: int | None = None
        self._actual_model: str | None = None
        self._lock = threading.Lock()
        self._closed = False
        self._cm: Any = None  # async context manager for spawn

    def _child_env(self) -> dict[str, str]:
        env = os.environ.copy()
        # Strip nothing globally; only ensure fixed safety env + allowlisted credentials.
        for k, v in self.descriptor.fixed_env.items():
            env[str(k)] = str(v)
        for name in self.descriptor.credential_env_names:
            if name in os.environ:
                env[name] = os.environ[name]
        if self.api_key_env and self.api_key_env in os.environ:
            env[self.api_key_env] = os.environ[self.api_key_env]
        env.update(self._extra_env)
        return env

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop
        loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        t = threading.Thread(target=_run, name=f"acp-loop-{self.entry_id}", daemon=True)
        t.start()
        self._loop = loop
        self._thread = t
        return loop

    def _run(self, coro: Any, *, timeout: float) -> Any:
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)

    async def _spawn_and_init(self, *, cwd: str) -> None:
        import acp
        from acp.stdio import spawn_agent_process

        client = _BoraAcpClient()
        self._client = client
        cmd = self._command_override or list(self.descriptor.acp_command)
        if not cmd:
            raise RuntimeError("acp_entry_missing")
        command, *args = cmd
        env = self._child_env()

        if self._process_launcher is not None:
            # Custom launcher must yield (conn, process) compatible pair or set streams.
            self._cm = self._process_launcher(client, command, *args, env=env, cwd=cwd)
            self._conn, self._process = await self._cm.__aenter__()
        else:
            # Host entry uses package workdir. docker-exec override must not
            # chdir the docker client into a container path.
            spawn_cwd = None if self._command_override else cwd
            self._cm = spawn_agent_process(
                client, command, *args, env=env, cwd=spawn_cwd
            )
            self._conn, self._process = await self._cm.__aenter__()

        from acp.schema import Implementation

        # No IDE filesystem/terminal proxy capabilities (tools run in entry process).
        init = await self._conn.initialize(
            protocol_version=acp.PROTOCOL_VERSION,
            client_capabilities=None,
            client_info=Implementation(name="bora", version=BORA_VERSION),
        )
        if init is None:
            raise RuntimeError("acp_protocol_error")

        self._protocol_version = getattr(init, "protocol_version", None) or 1
        agent_info = getattr(init, "agent_info", None)
        if agent_info is not None:
            if hasattr(agent_info, "model_dump"):
                self._agent_info = agent_info.model_dump(by_alias=True, exclude_none=True)
            else:
                self._agent_info = {
                    "name": getattr(agent_info, "name", None),
                    "version": getattr(agent_info, "version", None),
                }

        new = await self._conn.new_session(cwd=cwd, mcp_servers=[])
        self._acp_session_id = getattr(new, "session_id", None)
        if not self._acp_session_id:
            raise RuntimeError("acp_protocol_error")

        await self._bind_model(new)

    async def _bind_model(self, new_session_resp: Any) -> None:
        desired = self.model
        if self.descriptor.model_binding == "entry-default-only":
            if desired not in ("entry-default", "", None):
                raise RuntimeError("acp_model_unavailable")
            # Record whatever the entry uses by default if present.
            self._actual_model = "entry-default"
            return

        config_options = getattr(new_session_resp, "config_options", None) or getattr(
            new_session_resp, "configOptions", None
        )
        if config_options:
            for opt in config_options:
                category = getattr(opt, "category", None) or (
                    opt.get("category") if isinstance(opt, dict) else None
                )
                if category != "model":
                    continue
                config_id = getattr(opt, "id", None) or (
                    opt.get("id") if isinstance(opt, dict) else None
                )
                current = getattr(opt, "current_value", None) or getattr(opt, "currentValue", None)
                options = getattr(opt, "options", None) or (
                    opt.get("options") if isinstance(opt, dict) else None
                )
                values: list[str] = []
                if options:
                    for o in options:
                        val = getattr(o, "value", None) or (
                            o.get("value") if isinstance(o, dict) else None
                        )
                        if val is not None:
                            values.append(str(val))
                if desired == "entry-default":
                    self._actual_model = str(current) if current is not None else "entry-default"
                    return
                if desired in values:
                    await self._conn.set_config_option(
                        config_id=str(config_id),
                        session_id=self._acp_session_id,
                        value=desired,
                    )
                    self._actual_model = desired
                    return
                # exact match failed
                raise RuntimeError("acp_model_unavailable")

        # Some agents expose models differently (e.g. codex models.availableModels).
        models = getattr(new_session_resp, "models", None)
        if models is not None:
            available = getattr(models, "available_models", None) or getattr(
                models, "availableModels", None
            )
            if available and desired != "entry-default":
                ids = []
                for m in available:
                    mid = getattr(m, "model_id", None) or getattr(m, "modelId", None)
                    if mid:
                        ids.append(str(mid))
                if desired not in ids and not any(desired in i for i in ids):
                    raise RuntimeError("acp_model_unavailable")
            self._actual_model = desired if desired != "entry-default" else "entry-default"
            return

        # No model surface — accept entry default only.
        if desired not in ("entry-default",):
            # Soft: allow if entry has no config options (use as hint only).
            self._actual_model = desired
        else:
            self._actual_model = "entry-default"

    async def _prompt_once(self, prompt: str) -> AgentResult:
        import acp

        assert self._conn is not None and self._client is not None
        assert self._acp_session_id is not None
        # Per-prompt isolation: chunks + event buffer reset each invoke so
        # turn-level trajectory merge does not pull prior turns' stream.
        self._client.text_chunks.clear()
        self._client.events.clear()
        self._client.permission_decisions.clear()
        self._client.usage = None

        try:
            resp = await self._conn.prompt(
                session_id=self._acp_session_id,
                prompt=[acp.text_block(prompt)],
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "auth" in msg:
                err = "acp_auth_required"
            elif "eof" in msg or "closed" in msg:
                err = "acp_unexpected_eof"
            else:
                err = "acp_protocol_error"
            return self._result(
                text="".join(self._client.text_chunks),
                ok=False,
                error=err,
                stop=None,
            )

        stop = getattr(resp, "stop_reason", None) or getattr(resp, "stopReason", None)
        text = "".join(self._client.text_chunks)
        ok, err = _map_stop_reason(str(stop) if stop is not None else "end_turn")
        # Elicitation decline may have been recorded
        elicited = any(e.get("type") == "elicitation" for e in self._client.events[-5:])
        if elicited and not text:
            return self._result(
                text=text, ok=False, error="acp_elicitation_required", stop=stop
            )
        return self._result(text=text, ok=ok, error=err, stop=stop)

    def _result(
        self,
        *,
        text: str,
        ok: bool,
        error: str | None,
        stop: Any,
    ) -> AgentResult:
        structured = parse_validated_text_structured(text) if ok else None
        meta = {
            "executor_kind": "acp",
            "acp_entry_id": self.entry_id,
            "acp_version": self.descriptor.acp_version,
            "descriptor_digest": self.descriptor.descriptor_digest,
            "protocol_version": self._protocol_version,
            "agent_info": self._agent_info,
            "locked_model": self.model,
            "actual_model": self._actual_model,
            "stop_reason": str(stop) if stop is not None else None,
            "integration_mode": self.descriptor.integration_mode,
        }
        events = tuple(self._client.events) if self._client else ()
        usage = self._client.usage if self._client else None
        return AgentResult(
            model=str(self._actual_model or self.model),
            text=text,
            structured=structured,
            ok=ok,
            error=error,
            events=events,
            usage=usage,
            metadata=meta,
        )

    def _ensure_session(self, *, workdir: str | None, timeout: float) -> str | None:
        """Start ACP process/session if needed. Returns error kind or None."""
        with self._lock:
            if self._closed:
                return "session_closed"
            if self._conn is not None and self._acp_session_id is not None:
                return None
        # Host PATH readiness only when launching locally. L1 uses command_override
        # (docker exec) and image BOM preflight for entry presence.
        if self._command_override is None and self._process_launcher is None:
            ready = readiness_for(self.descriptor)
            if ready["readiness"] != "ready":
                return str(ready["readiness"]).replace("-", "_")
        cwd = workdir or self.workdir or os.getcwd()
        try:
            self._run(self._spawn_and_init(cwd=cwd), timeout=min(timeout, 120.0))
        except RuntimeError as exc:
            return str(exc) or "acp_protocol_error"
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "auth" in msg:
                return "acp_auth_required"
            return "acp_protocol_error"
        return None

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 300.0,
        workdir: str | None = None,
        collect_dir: str | Path | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        if os.environ.get("BORA_OFFLINE_AGENT") == "1":
            return _offline_result(self.model)

        err = self._ensure_session(workdir=workdir, timeout=timeout)
        if err is not None:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=err,
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "reason": err,
                        "source": "acp_adapter",
                    },
                ),
                metadata={
                    "executor_kind": "acp",
                    "acp_entry_id": self.entry_id,
                    "descriptor_digest": self.descriptor.descriptor_digest,
                },
            )

        started = time.monotonic()
        try:
            result = self._run(self._prompt_once(prompt), timeout=timeout)
        except TimeoutError:
            with contextlib_suppress(Exception):
                self._run(self._cancel(), timeout=5.0)
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="acp_timeout",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "timeout",
                        "source": "acp_adapter",
                        "elapsed_ms": (time.monotonic() - started) * 1000.0,
                    },
                ),
                metadata={
                    "executor_kind": "acp",
                    "acp_entry_id": self.entry_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="acp_protocol_error",
                stderr=str(exc)[:500],
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "error_type": type(exc).__name__,
                        "source": "acp_adapter",
                    },
                ),
                metadata={
                    "executor_kind": "acp",
                    "acp_entry_id": self.entry_id,
                },
            )

        if collect_dir is not None:
            root = Path(collect_dir)
            root.mkdir(parents=True, exist_ok=True)
            if result.events:
                (root / "acp_events.jsonl").write_text(
                    "\n".join(
                        json.dumps(e, ensure_ascii=False, sort_keys=True)
                        for e in result.events
                    )
                    + "\n",
                    encoding="utf-8",
                )
            # Training-oriented full stream (parent of collect_dir is invocation dir
            # when collect_dir is .../backend_raw).
            inv_dir = root.parent if root.name == "backend_raw" else root
            write_trajectory_jsonl(
                inv_dir,
                prompt=prompt,
                events=result.events,
                final_text=result.text,
                structured=result.structured,
                usage=result.usage,
                ok=result.ok,
                error=result.error,
                metadata=result.metadata,
            )
        return result

    async def _cancel(self) -> None:
        if self._conn is not None and self._acp_session_id is not None:
            with contextlib_suppress(Exception):
                await self._conn.cancel(session_id=self._acp_session_id)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            if self._loop is not None:

                async def _shutdown() -> None:
                    if self._conn is not None and self._acp_session_id is not None:
                        with contextlib_suppress(Exception):
                            await self._conn.close_session(session_id=self._acp_session_id)
                    if self._cm is not None:
                        with contextlib_suppress(Exception):
                            await self._cm.__aexit__(None, None, None)
                    if self._process is not None:
                        with contextlib_suppress(Exception):
                            self._process.terminate()

                with contextlib_suppress(Exception):
                    self._run(_shutdown(), timeout=10.0)
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(self._loop.stop)
        finally:
            self._conn = None
            self._process = None
            self._acp_session_id = None


def resolve_acp_executor(
    *,
    entry_id: str,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    **_kw: Any,
) -> AcpExecutor:
    return AcpExecutor(
        entry_id=entry_id,
        model=model,
        base_url=base_url,
        api_key_env=api_key,
    )
