"""Wire L0/L5 extension multi-slots around production prepare/run/evaluate/cleanup.

Uses the first agent profile's resolved graph when present; otherwise a
defaults-only resolve. Prepare/bake-related failures fail closed when requested;
observational hooks (run/evaluate/cleanup) may continue after recording errors.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any

from bora.config.model import LockedTaskConfig, thaw
from bora.plugins.bootstrap import ensure_bootstrapped
from bora.plugins.lifecycle import emit_cleanup, emit_evaluate, emit_prepare, emit_run
from bora.plugins.protocol import BindingIntent, ExtensionGraph, intent_from_profile
from bora.plugins.resolve import resolve

_LOG = logging.getLogger(__name__)


def graph_for_lock(lock: LockedTaskConfig) -> ExtensionGraph:
    """Resolve one ExtensionGraph for lifecycle emit (first profile or empty intent)."""
    reg = ensure_bootstrapped()
    profiles = thaw(lock.agent_profiles) if lock.agent_profiles else []
    if isinstance(profiles, list) and profiles:
        first = profiles[0]
        if isinstance(first, dict):
            intent = intent_from_profile(first)
            if not intent.profile_id:
                intent.profile_id = str(first.get("id") or "default")
            return resolve(intent, reg, materialize=False)
    return resolve(BindingIntent(profile_id="_lifecycle"), reg, materialize=False)


def _run(coro: Any) -> Any:
    """Drive an async hook coroutine to completion.

    Always awaits — never drops an unawaited coroutine. When already inside a
    running event loop, execute on a worker thread with ``asyncio.run``.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def hook_prepare(
    lock: LockedTaskConfig,
    value: Any = None,
    *,
    fail_closed: bool = True,
) -> Any:
    """Emit before/after_prepare. Default fail_closed (Spec 05 C2 bake/prepare)."""
    graph = graph_for_lock(lock)
    try:
        return _run(emit_prepare(graph, value))
    except Exception:
        if fail_closed:
            raise
        _LOG.exception("extension hook_prepare failed (fail-open)")
        return value


def hook_run(lock: LockedTaskConfig, value: Any = None) -> Any:
    """Emit before/after_run. Observational: record and continue on error."""
    graph = graph_for_lock(lock)
    try:
        return _run(emit_run(graph, value))
    except Exception:
        _LOG.exception("extension hook_run failed (fail-open)")
        return value


def hook_evaluate(lock: LockedTaskConfig, value: Any = None) -> Any:
    """Emit before/after_evaluate. Observational: record and continue on error."""
    graph = graph_for_lock(lock)
    try:
        return _run(emit_evaluate(graph, value))
    except Exception:
        _LOG.exception("extension hook_evaluate failed (fail-open)")
        return value


def hook_cleanup(lock: LockedTaskConfig, value: Any = None) -> Any:
    """Emit cleanup bookends + cleanup_actions/report. Observational fail-open."""
    graph = graph_for_lock(lock)
    try:
        return _run(emit_cleanup(graph, value))
    except Exception:
        _LOG.exception("extension hook_cleanup failed (fail-open)")
        return value
