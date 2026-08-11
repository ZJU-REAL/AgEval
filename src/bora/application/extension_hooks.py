"""Wire L0/L5 extension multi-slots around production prepare/run/evaluate/cleanup.

Uses the first agent profile's resolved graph when present; otherwise a
defaults-only resolve. Fail-open on hook errors so phase emit cannot crash score.
"""

from __future__ import annotations

import asyncio
from typing import Any

from bora.config.model import LockedTaskConfig, thaw
from bora.plugins.bootstrap import ensure_bootstrapped
from bora.plugins.lifecycle import emit_cleanup, emit_evaluate, emit_prepare, emit_run
from bora.plugins.protocol import BindingIntent, ExtensionGraph, intent_from_profile
from bora.plugins.resolve import resolve


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
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # Nested event loop (rare): skip hooks rather than crash Attempt.
        return None


def hook_prepare(lock: LockedTaskConfig, value: Any = None) -> Any:
    graph = graph_for_lock(lock)
    with_suppress = True
    try:
        return _run(emit_prepare(graph, value))
    except Exception:  # noqa: BLE001
        if with_suppress:
            return value
        raise


def hook_run(lock: LockedTaskConfig, value: Any = None) -> Any:
    graph = graph_for_lock(lock)
    try:
        return _run(emit_run(graph, value))
    except Exception:  # noqa: BLE001
        return value


def hook_evaluate(lock: LockedTaskConfig, value: Any = None) -> Any:
    graph = graph_for_lock(lock)
    try:
        return _run(emit_evaluate(graph, value))
    except Exception:  # noqa: BLE001
        return value


def hook_cleanup(lock: LockedTaskConfig, value: Any = None) -> Any:
    graph = graph_for_lock(lock)
    try:
        return _run(emit_cleanup(graph, value))
    except Exception:  # noqa: BLE001
        return value
