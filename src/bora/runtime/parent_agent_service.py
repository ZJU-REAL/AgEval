"""Parent-owned Agent Service: session bind + pre-spawn hard ceiling + trajectory.

Worker/SDK only holds an opaque session id and talks over a Unix socket.
Shared application code does not branch on benchmark/task names.
Each parent-bound invoke writes per-invocation evidence before returning.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bora.evidence.redaction import RedactionError
from bora.evidence.store import AttemptEvidenceStore
from bora.runtime.agent_service_evidence import (
    map_error_status,
    seal_failure,
    seal_invoke_result,
    write_invoke_request,
)

# Default per-invoke ceiling when package does not declare one.
DEFAULT_INVOKE_TIMEOUT_SECONDS = 300.0


def resolve_invoke_timeout_seconds(
    params: dict[str, Any] | None = None,
    *,
    default: float = DEFAULT_INVOKE_TIMEOUT_SECONDS,
) -> float:
    """Read package ``parameters.agent_timeout_seconds`` (or alias).

    Also accepts ``agent_invoke_timeout_seconds``. Non-positive / missing → default.
    """
    data = params if isinstance(params, dict) else {}
    raw = data.get("agent_timeout_seconds")
    if raw is None:
        raw = data.get("agent_invoke_timeout_seconds")
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(default)
    return value if value > 0 else float(default)


@dataclass
class SessionBinding:
    session_id: str
    attempt_id: str
    profile_id: str
    model: str
    executor_kind: str
    # Optional profile routing (lock-safe): base_url + api_key env *locator* name.
    base_url: str | None = None
    api_key: str | None = None
    # Spec 19: ACP registry entry id when executor_kind == "acp".
    acp_entry_id: str | None = None
    # L1 multi-actor binding (opaque target id only — no docker handle).
    actor_id: str | None = None
    target_id: str | None = None
    generation: int | None = None
    closed: bool = False


@dataclass
class ParentAgentService:
    """Process-local parent authority for Agent invocations."""

    profiles: list[dict[str, Any]]
    agent_invocation_limit: int
    resolve_executor: Callable[..., Any]
    attempt_id: str  # Runtime-owned; never taken from Harness client
    offline_env: str = "BORA_OFFLINE_AGENT"
    evidence_store: AttemptEvidenceStore | None = None
    # Wall hard ceiling (monotonic seconds); checked before each external invoke.
    deadline_monotonic: float | None = None
    # Per-invoke executor timeout (seconds). Default 300; packages set via
    # ``parameters.agent_timeout_seconds`` (wired by run_l1 / run_command).
    # Operator override: env ``BORA_AGENT_INVOKE_TIMEOUT`` (seconds).
    invoke_timeout_seconds: float = 300.0
    # L1: require actor_id; validate against logical topology; bind target generation.
    require_actor_id: bool = False
    # Callable(actor_id, profile_id) -> dict with ok/error/target_id/generation or fail.
    validate_actor_profile: Callable[[str, str], dict[str, Any]] | None = None
    # When set, builds container-bound executor from SessionBinding (L1 only).
    # Signature: (binding: SessionBinding) -> executor with .invoke(...)
    make_target_executor: Callable[[SessionBinding], Any] | None = None
    # Forbid host resolve_executor path (L1 no-fallback).
    l1_container_only: bool = False
    _remaining: int = field(init=False)
    _sessions: dict[str, SessionBinding] = field(default_factory=dict)
    # Reuse executor instances across multi-invoke BORA sessions (ACP process/session).
    _executors: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    invocations_completed: int = 0
    host_fallback_count: int = 0

    def __post_init__(self) -> None:
        self._remaining = max(0, int(self.agent_invocation_limit))
        # Normalize non-positive package values to default.
        try:
            t = float(self.invoke_timeout_seconds)
        except (TypeError, ValueError):
            t = DEFAULT_INVOKE_TIMEOUT_SECONDS
        self.invoke_timeout_seconds = t if t > 0 else DEFAULT_INVOKE_TIMEOUT_SECONDS

    def _wall_expired(self) -> bool:
        return self.deadline_monotonic is not None and time.monotonic() >= self.deadline_monotonic

    def _resolve_invoke_timeout(self) -> float:
        """Seconds for this executor.invoke call.

        Priority: env ``BORA_AGENT_INVOKE_TIMEOUT`` > service field; then
        capped by remaining wall deadline when armed.
        """
        timeout = float(self.invoke_timeout_seconds)
        env_raw = os.environ.get("BORA_AGENT_INVOKE_TIMEOUT", "").strip()
        if env_raw:
            with contextlib.suppress(ValueError):
                env_t = float(env_raw)
                if env_t > 0:
                    timeout = env_t
        timeout = max(1.0, timeout)
        if self.deadline_monotonic is not None:
            remaining = self.deadline_monotonic - time.monotonic()
            if remaining <= 0:
                return 0.1
            timeout = min(timeout, remaining)
        return timeout

    def open_session(self, *, profile_id: str, actor_id: str | None = None) -> dict[str, Any]:
        if self._wall_expired():
            return {"ok": False, "error": "wall_time_exceeded", "profile_id": profile_id}
        if self.require_actor_id and (not actor_id or not str(actor_id).strip()):
            return {
                "ok": False,
                "error": "actor_id_required",
                "profile_id": profile_id,
            }
        actor_id_n = str(actor_id).strip() if actor_id else None
        profile = next((p for p in self.profiles if p.get("id") == profile_id), None)
        if profile is None:
            return {"ok": False, "error": "unknown_profile", "profile_id": profile_id}

        target_id: str | None = None
        generation: int | None = None
        if actor_id_n is not None and self.validate_actor_profile is not None:
            check = self.validate_actor_profile(actor_id_n, profile_id)
            if not check.get("ok"):
                return {
                    "ok": False,
                    "error": str(check.get("error") or "actor_profile_denied"),
                    "profile_id": profile_id,
                    "actor_id": actor_id_n,
                }
            target_id = check.get("target_id")  # type: ignore[assignment]
            generation = check.get("generation")  # type: ignore[assignment]
            if target_id is not None:
                target_id = str(target_id)
            if generation is not None:
                generation = int(generation)

        base_url_raw = profile.get("base_url")
        base_url = (
            str(base_url_raw).strip()
            if isinstance(base_url_raw, str) and base_url_raw.strip()
            else None
        )
        api_key_raw = profile.get("api_key")
        api_key = (
            str(api_key_raw).strip()
            if isinstance(api_key_raw, str) and api_key_raw.strip()
            else None
        )
        executor_kind = str(profile.get("executor") or "acp")
        acp_entry_id: str | None = None
        if executor_kind == "acp":
            options = profile.get("options") if isinstance(profile.get("options"), dict) else {}
            entry_raw = options.get("entry") if isinstance(options, dict) else None
            if isinstance(entry_raw, str) and entry_raw.strip():
                acp_entry_id = entry_raw.strip()
            else:
                return {
                    "ok": False,
                    "error": "acp_entry_required",
                    "profile_id": profile_id,
                }
        with self._lock:
            sid = f"sess_{uuid.uuid4().hex[:16]}"
            binding = SessionBinding(
                session_id=sid,
                attempt_id=self.attempt_id,
                profile_id=profile_id,
                model=str(profile.get("model") or "gpt-5.4-mini"),
                executor_kind=executor_kind,
                base_url=base_url,
                api_key=api_key,
                acp_entry_id=acp_entry_id,
                actor_id=actor_id_n,
                target_id=target_id,
                generation=generation,
            )
            self._sessions[sid] = binding
            return {
                "ok": True,
                "session_id": sid,
                "profile_id": profile_id,
                "actor_id": actor_id_n,
                "target_id": target_id,  # opaque only
                "generation": generation,
                "attempt_id": self.attempt_id,
                "provider_session_handle": None,
                "acp_entry_id": acp_entry_id,
            }

    def invoke(self, *, session_id: str, prompt: str) -> dict[str, Any]:
        # Wall hard ceiling: refuse before external executor effect.
        if self._wall_expired():
            return {
                "ok": False,
                "error": "wall_time_exceeded",
                "text": "",
                "structured": None,
                "provider_session_handle": None,
            }
        with self._lock:
            binding = self._sessions.get(session_id)
            if binding is None:
                return {"ok": False, "error": "unknown_session"}
            if binding.closed:
                return {"ok": False, "error": "session_closed"}
            if binding.attempt_id != self.attempt_id:
                return {"ok": False, "error": "cross_attempt_session"}
            if self._remaining <= 0:
                return {"ok": False, "error": "agent_invocation_limit"}
            # Reserve before spawn (no refund on failure).
            self._remaining -= 1
            kind = binding.executor_kind
            model = binding.model
            profile_id = binding.profile_id
            base_url = binding.base_url
            api_key = binding.api_key
            acp_entry_id = binding.acp_entry_id
            binding_snap = binding
            actor_id = binding.actor_id
            target_id = binding.target_id
            generation = binding.generation
            cached_executor = self._executors.get(session_id)

        handle = None
        started = time.monotonic()
        if self.evidence_store is not None:
            handle = self.evidence_store.begin_invocation(
                profile_id=profile_id,
                executor_kind=kind,
                model=model,
            )
            try:
                write_invoke_request(
                    handle,
                    prompt=prompt,
                    profile_id=profile_id,
                    kind=kind,
                    model=model,
                    base_url=base_url,
                    api_key=api_key,
                    acp_entry_id=acp_entry_id,
                    actor_id=actor_id,
                    target_id=target_id,
                    generation=generation,
                    l1_container_only=self.l1_container_only,
                )
            except RedactionError:
                # Already sealed as redaction_failed by store.
                with self._lock:
                    self.invocations_completed += 1
                return {
                    "ok": False,
                    "error": "redaction_failed",
                    "model": model,
                    "text": "",
                    "structured": None,
                    "provider_session_handle": None,
                    "remaining_after": self._remaining,
                    "invocation_id": handle.invocation_id if handle else None,
                    "evidence_relative": handle.relative_path if handle else None,
                }

        try:
            if cached_executor is not None:
                executor = cached_executor
            elif self.make_target_executor is not None and binding_snap is not None:
                # L1 container path — never fall through to host resolve_executor.
                executor = self.make_target_executor(binding_snap)
                with self._lock:
                    self._executors[session_id] = executor
            elif self.l1_container_only:
                seal_failure(
                    handle,
                    status="failed",
                    error="l1_executor_unbound",
                    latency_ms=(time.monotonic() - started) * 1000.0,
                )
                return {
                    "ok": False,
                    "error": "l1_executor_unbound",
                    "executor": kind,
                    "invocation_id": handle.invocation_id if handle else None,
                    "evidence_relative": handle.relative_path if handle else None,
                }
            else:
                try:
                    executor = self.resolve_executor(
                        kind,
                        model=model,
                        base_url=base_url,
                        api_key=api_key,
                        entry=acp_entry_id,
                        entry_id=acp_entry_id,
                    )
                except TypeError:
                    # Older resolve_executor callables may only accept kind/model.
                    executor = self.resolve_executor(kind, model=model)
                with self._lock:
                    self._executors[session_id] = executor
        except KeyError:
            seal_failure(
                handle,
                status="failed",
                error="executor_unknown",
                latency_ms=(time.monotonic() - started) * 1000.0,
            )
            return {
                "ok": False,
                "error": "executor_unknown",
                "executor": kind,
                "invocation_id": handle.invocation_id if handle else None,
                "evidence_relative": handle.relative_path if handle else None,
            }
        except Exception as exc:  # noqa: BLE001 — target bind failures fail closed
            if self.l1_container_only:
                # Explicitly never host-fallback.
                err = getattr(exc, "error", None) or type(exc).__name__
                seal_failure(
                    handle,
                    status="failed",
                    error=str(err),
                    latency_ms=(time.monotonic() - started) * 1000.0,
                )
                return {
                    "ok": False,
                    "error": str(err),
                    "executor": kind,
                    "invocation_id": handle.invocation_id if handle else None,
                    "evidence_relative": handle.relative_path if handle else None,
                }
            raise

        collect_dir = None
        if handle is not None:
            collect_dir = handle.directory / "backend_raw"
            collect_dir.mkdir(parents=True, exist_ok=True)

        # Mechanism test hook: force typed partial terminal on N-th invocation
        # (1-based). Values: crash | timeout | cancel | failed. Never invents PASS.
        force_err = os.environ.get("BORA_FORCE_INVOCATION_ERROR", "").strip()
        force_n = os.environ.get("BORA_FORCE_INVOCATION_N", "2").strip()
        try:
            force_at = int(force_n)
        except ValueError:
            force_at = 2
        next_n = self.invocations_completed + 1
        if force_err and next_n == force_at:
            latency = (time.monotonic() - started) * 1000.0
            status = map_error_status(force_err if force_err != "crash" else "crash")
            if force_err == "crash":
                status = "crash"
            if handle is not None:
                handle.append_event(
                    {
                        "type": "lifecycle",
                        "phase": status,
                        "source": "force_hook",
                        "forced": force_err,
                    }
                )
                if force_err == "crash":
                    seal_failure(handle, status="crash", error="forced_crash", latency_ms=latency)
                else:
                    allowed = {"timeout", "cancelled", "failed", "crash"}
                    seal_status = status if status in allowed else "failed"
                    seal_failure(
                        handle,
                        status=seal_status,
                        error=f"forced_{force_err}",
                        latency_ms=latency,
                    )
            with self._lock:
                self.invocations_completed += 1
            return {
                "ok": False,
                "error": f"forced_{force_err}",
                "model": model,
                "text": "",
                "structured": None,
                "provider_session_handle": None,
                "remaining_after": self._remaining,
                "invocation_id": handle.invocation_id if handle else None,
                "evidence_relative": handle.relative_path if handle else None,
            }

        sentinels = tuple(self.evidence_store.sentinels) if self.evidence_store else ()
        invoke_timeout = self._resolve_invoke_timeout()
        try:
            # Multi-invoke sessions need headroom beyond the codex default 45s.
            # Timeout is service-configured (package parameters / env), not hardcoded.
            try:
                result = executor.invoke(
                    prompt,
                    timeout=invoke_timeout,
                    collect_dir=collect_dir,
                    redaction_sentinels=sentinels,
                )
            except TypeError:
                try:
                    result = executor.invoke(
                        prompt, timeout=invoke_timeout, collect_dir=collect_dir
                    )
                except TypeError:
                    try:
                        result = executor.invoke(prompt, timeout=invoke_timeout)
                    except TypeError:
                        result = executor.invoke(prompt)
        except Exception as exc:  # noqa: BLE001 — executor crash must leave partial evidence
            latency = (time.monotonic() - started) * 1000.0
            if handle is not None:
                handle.append_event(
                    {
                        "type": "lifecycle",
                        "phase": "crash",
                        "error_type": type(exc).__name__,
                        "source": "agent_service",
                    }
                )
                seal_failure(
                    handle,
                    status="crash",
                    error=type(exc).__name__,
                    latency_ms=latency,
                )
            with self._lock:
                self.invocations_completed += 1
            return {
                "ok": False,
                "error": type(exc).__name__,
                "model": model,
                "text": "",
                "structured": None,
                "provider_session_handle": None,
                "remaining_after": self._remaining,
                "invocation_id": handle.invocation_id if handle else None,
                "evidence_relative": handle.relative_path if handle else None,
            }

        latency = (time.monotonic() - started) * 1000.0
        if handle is not None:
            redaction_err = seal_invoke_result(
                handle,
                result=result,
                prompt=prompt,
                kind=kind,
                turn_index=self.invocations_completed + 1,
                latency_ms=latency,
            )
            if redaction_err is not None:
                with self._lock:
                    self.invocations_completed += 1
                return {
                    "ok": False,
                    "error": "redaction_failed",
                    "model": result.model,
                    "text": "",
                    "structured": None,
                    "provider_session_handle": None,
                    "remaining_after": self._remaining,
                    "invocation_id": handle.invocation_id,
                    "evidence_relative": handle.relative_path,
                }

        with self._lock:
            self.invocations_completed += 1
        return {
            "ok": bool(result.ok),
            "error": result.error,
            "model": result.model,
            "text": (result.text or "")[-4000:],
            "structured": result.structured if isinstance(result.structured, dict) else None,
            "provider_session_handle": None,
            "remaining_after": self._remaining,
            "invocation_id": handle.invocation_id if handle else None,
            "evidence_relative": handle.relative_path if handle else None,
        }

    def close_session(self, *, session_id: str) -> dict[str, Any]:
        with self._lock:
            binding = self._sessions.get(session_id)
            if binding is None:
                return {"ok": True, "already": "missing"}
            binding.closed = True
            executor = self._executors.pop(session_id, None)
        if executor is not None and hasattr(executor, "close"):
            with contextlib.suppress(Exception):
                executor.close()
        return {"ok": True}
