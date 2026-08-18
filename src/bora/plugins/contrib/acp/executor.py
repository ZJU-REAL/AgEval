"""AcpExecutor: parent-side ACP process/session invoke (Spec 19)."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress as contextlib_suppress
from pathlib import Path
from typing import Any

from bora import __version__ as BORA_VERSION
from bora.adapters.agent_contract import (
    AgentExecutor,
    AgentResult,
    parse_validated_text_structured,
)
from bora.plugins.contrib.acp.client import (
    _BoraAcpClient,
    _map_stop_reason,
    _offline_result,
)
from bora.plugins.contrib.acp.registry import AcpEntryDescriptor, get_entry, readiness_for
from bora.plugins.contrib.acp.trajectory_map import acp_session_events_to_bora
from bora.plugins.contrib.acp.types import ProcessLauncher
from bora.plugins.contrib.acp.usage import _as_plain_mapping, normalize_acp_usage

# Advertised ACP config option ids that mean thinking / reasoning effort.
# Category ``thought_level`` is the protocol selector; these ids cover entries
# that omit the category or use a vendor-shaped id.
_REASONING_OPTION_IDS = frozenset(
    {"thought_level", "reasoning_effort", "reasoning", "thinking", "effort"}
)


def _field(obj: Any, *names: str) -> Any:
    """Read a snake_case or camelCase attribute / mapping key."""
    if obj is None:
        return None
    for name in names:
        if isinstance(obj, dict) and name in obj:
            val = obj[name]
            if val is not None:
                return val
        val = getattr(obj, name, None)
        if val is not None:
            return val
    return None


def _config_options_from(obj: Any) -> Any:
    return _field(obj, "config_options", "configOptions")


def _select_option_values(opt: Any) -> list[str]:
    """Flatten a select option's values, including grouped choices."""
    raw = _field(opt, "options")
    if not raw:
        return []
    values: list[str] = []
    for item in raw:
        grouped = _field(item, "options")
        own = _field(item, "value")
        if grouped and own is None:
            for child in grouped:
                val = _field(child, "value")
                if val is not None:
                    values.append(str(val))
            continue
        if own is not None:
            values.append(str(own))
    return values


def _find_reasoning_config_option(config_options: Any) -> Any:
    """First advertised thinking selector (category, then known ids)."""
    if not config_options:
        return None
    by_id = None
    for opt in config_options:
        if _field(opt, "category") == "thought_level":
            return opt
        oid = _field(opt, "id")
        if by_id is None and oid in _REASONING_OPTION_IDS:
            by_id = opt
    return by_id


class AcpExecutor(AgentExecutor):
    """Descriptor-driven ACP executor; one process/session per BORA session reuse."""

    kind: str = "acp"

    def __init__(
        self,
        *,
        entry_id: str,
        model: str = "entry-default",
        reasoning_effort: str | None = None,
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
        self.reasoning_effort = reasoning_effort.strip() if reasoning_effort else None
        if self.reasoning_effort == "":
            self.reasoning_effort = None
        self.base_url = base_url
        self.api_key_env = api_key_env
        resolved = descriptor if descriptor is not None else get_entry(entry_id)
        if resolved is None:
            raise KeyError(f"unknown_acp_entry:{entry_id}")
        self.descriptor: AcpEntryDescriptor = resolved
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
        self._actual_reasoning_effort: str | None = None
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
            self._cm = spawn_agent_process(client, command, *args, env=env, cwd=spawn_cwd)
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

        latest = await self._bind_model(new)
        await self._bind_reasoning_effort(latest)

    async def _bind_model(self, new_session_resp: Any) -> Any:
        """Bind model. Returns the latest ``configOptions`` (refreshed after set)."""
        desired = self.model
        initial = _config_options_from(new_session_resp)
        if self.descriptor.model_binding == "entry-default-only":
            if desired not in ("entry-default", "", None):
                raise RuntimeError("acp_model_unavailable")
            # Record whatever the entry uses by default if present.
            self._actual_model = "entry-default"
            return initial

        if initial:
            for opt in initial:
                if _field(opt, "category") != "model":
                    continue
                config_id = _field(opt, "id")
                current = _field(opt, "current_value", "currentValue")
                values = _select_option_values(opt)
                if desired == "entry-default":
                    self._actual_model = str(current) if current is not None else "entry-default"
                    return initial
                if desired in values:
                    resp = await self._conn.set_config_option(
                        config_id=str(config_id),
                        session_id=self._acp_session_id,
                        value=desired,
                    )
                    self._actual_model = desired
                    return _config_options_from(resp) or initial
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
            return initial

        # No model surface — accept entry default only.
        if desired not in ("entry-default",):
            # Soft: allow if entry has no config options (use as hint only).
            self._actual_model = desired
        else:
            self._actual_model = "entry-default"
        return initial

    async def _bind_reasoning_effort(self, config_options: Any) -> None:
        """Apply profile ``options.reasoning_effort`` to the advertised selector."""
        desired = self.reasoning_effort
        if not desired:
            return
        opt = _find_reasoning_config_option(config_options)
        if opt is None:
            raise RuntimeError("acp_reasoning_effort_unavailable")
        config_id = _field(opt, "id")
        current = _field(opt, "current_value", "currentValue")
        values = _select_option_values(opt)
        if current is not None and desired == str(current):
            self._actual_reasoning_effort = desired
            return
        if not config_id or desired not in values:
            raise RuntimeError("acp_reasoning_effort_unavailable")
        await self._conn.set_config_option(
            config_id=str(config_id),
            session_id=self._acp_session_id,
            value=desired,
        )
        self._actual_reasoning_effort = desired

    async def _prompt_once(self, prompt: str) -> AgentResult:
        import acp

        assert self._conn is not None and self._client is not None
        assert self._acp_session_id is not None
        # Per-prompt isolation: chunks + event buffer reset each invoke so
        # turn-level trajectory merge does not pull prior turns' stream.
        self._client.text_chunks.clear()
        self._client.events.clear()
        self._client.permission_decisions.clear()
        self._client.latest_usage_update = None
        self._client.prompt_usage = None

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

        # Token authority: PromptResponse.usage (may be absent on older agents).
        prompt_usage_raw = getattr(resp, "usage", None)
        self._client.prompt_usage = _as_plain_mapping(prompt_usage_raw)
        if self._client.prompt_usage is not None:
            event_prompt_usage: dict[str, Any] = self._client.prompt_usage
            if prompt_usage_raw is not None and hasattr(prompt_usage_raw, "model_dump"):
                with contextlib_suppress(Exception):
                    dumped_prompt = prompt_usage_raw.model_dump(by_alias=True, exclude_none=True)
                    if isinstance(dumped_prompt, dict):
                        event_prompt_usage = dumped_prompt
            self._client.record(
                {
                    "type": "prompt_usage",
                    "session_id": self._acp_session_id,
                    "source": "acp",
                    # Wire-ish camelCase when available for protocol cross-check.
                    "prompt_usage": event_prompt_usage,
                }
            )

        stop = getattr(resp, "stop_reason", None) or getattr(resp, "stopReason", None)
        text = "".join(self._client.text_chunks)
        ok, err = _map_stop_reason(str(stop) if stop is not None else "end_turn")
        # Elicitation decline may have been recorded
        elicited = any(e.get("type") == "elicitation" for e in self._client.events[-5:])
        if elicited and not text:
            return self._result(text=text, ok=False, error="acp_elicitation_required", stop=stop)
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
            "locked_reasoning_effort": self.reasoning_effort,
            "actual_reasoning_effort": self._actual_reasoning_effort,
            "stop_reason": str(stop) if stop is not None else None,
            "integration_mode": self.descriptor.integration_mode,
        }
        vendor_events = tuple(self._client.events) if self._client else ()
        events = tuple(acp_session_events_to_bora(vendor_events))
        # Dual-source normalize: tokens from PromptResponse.usage; cost/context
        # from latest UsageUpdate. Never maps context.used → input_tokens.
        usage = None
        if self._client is not None:
            usage = normalize_acp_usage(
                prompt_usage=self._client.prompt_usage,
                usage_update=self._client.latest_usage_update,
            )
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
        cwd = workdir or self.workdir
        if not cwd:
            return "acp_workdir_required"
        if self._command_override is None and self._process_launcher is None:
            ready = readiness_for(self.descriptor)
            if ready["readiness"] != "ready":
                return str(ready["readiness"]).replace("-", "_")
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
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        from bora.runtime.offline import is_offline_agent

        del redaction_sentinels
        if is_offline_agent():
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
            # Vendor-native ACP stream (layer A). Layer C is Core-owned.
            vendor = tuple(self._client.events) if self._client else ()
            dump = vendor or result.events
            if dump:
                (root / "acp_events.jsonl").write_text(
                    "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in dump)
                    + "\n",
                    encoding="utf-8",
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
