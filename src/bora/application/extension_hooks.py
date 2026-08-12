"""Wire L0–L5 extension multi-slots around production control points.

Uses the first agent profile's resolved graph when present; otherwise a
defaults-only resolve. Prepare/env/score-related failures fail closed when
requested; observational hooks may continue after recording errors.

#71: env/eval hooks await registered callables (SPI). No declaration-DSL
collectors that Core later interprets as free-form command rows.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any

from bora.config.model import LockedTaskConfig, thaw
from bora.plugins.bootstrap import ensure_bootstrapped
from bora.plugins.lifecycle import (
    call_env_action,
    call_evaluation_runtime,
    collect_evaluation_input,
    emit_cleanup,
    emit_env_inject,
    emit_env_prepare,
    emit_env_teardown,
    emit_evaluate,
    emit_prepare,
    emit_run,
    score_postprocess,
)
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


# --- #71 C: env lifecycle (executable middleware / SPI) ---


def hook_env_prepare(
    lock: LockedTaskConfig,
    value: Any,
    *,
    ctx: Any = None,
    fail_closed: bool = True,
) -> Any:
    """Run multi ``env_prepare_commands`` with live env handoff + ctx.

    Handlers may mutate the handoff, call ``ctx.env_manager``, run subprocesses,
    or write files. Host does **not** interpret a list of command dicts.
    """
    graph = graph_for_lock(lock)
    try:
        return _run(emit_env_prepare(graph, value, ctx=ctx))
    except Exception:
        if fail_closed:
            raise
        _LOG.exception("extension hook_env_prepare failed (fail-open)")
        return value


def hook_env_inject(
    lock: LockedTaskConfig,
    value: Any,
    *,
    ctx: Any = None,
    fail_closed: bool = True,
) -> Any:
    """Run multi ``env_inject`` to rewrite the env handoff object."""
    graph = graph_for_lock(lock)
    try:
        return _run(emit_env_inject(graph, value, ctx=ctx))
    except Exception:
        if fail_closed:
            raise
        _LOG.exception("extension hook_env_inject failed (fail-open)")
        return value


def hook_env_teardown(
    lock: LockedTaskConfig,
    value: Any = None,
    *,
    ctx: Any = None,
) -> Any:
    """Run multi ``env_teardown_commands`` before resource close (fail-open)."""
    graph = graph_for_lock(lock)
    try:
        return _run(emit_env_teardown(graph, value, ctx=ctx))
    except Exception:
        _LOG.exception("extension hook_env_teardown failed (fail-open)")
        return value


def hook_env_action(
    lock: LockedTaskConfig,
    value: Any = None,
    *,
    ctx: Any = None,
) -> Any:
    """Materialize single-winner ``env_action`` provide SPI (fail closed)."""
    graph = graph_for_lock(lock)
    try:
        return _run(call_env_action(graph, value, ctx=ctx))
    except Exception:
        _LOG.exception("extension hook_env_action failed")
        raise


# --- #71 D: evaluation adjacency ---


def hook_evaluation_input(
    lock: LockedTaskConfig,
    value: Any,
    *,
    ctx: Any = None,
) -> Any:
    """Multi ``evaluation_input_contribute`` (score-affecting; fail closed)."""
    graph = graph_for_lock(lock)
    try:
        return _run(collect_evaluation_input(graph, value, ctx=ctx))
    except Exception:
        _LOG.exception("extension hook_evaluation_input failed")
        raise


def hook_evaluation_runtime(
    lock: LockedTaskConfig,
    value: Any = None,
    *,
    ctx: Any = None,
) -> Any:
    """Single-winner ``evaluation_runtime`` provide (lock-visible; fail closed)."""
    graph = graph_for_lock(lock)
    try:
        return _run(call_evaluation_runtime(graph, value, ctx=ctx))
    except Exception:
        _LOG.exception("extension hook_evaluation_runtime failed")
        raise


def hook_score_postprocess(
    lock: LockedTaskConfig,
    value: Any,
    *,
    ctx: Any = None,
) -> Any:
    """Multi ``score_postprocess`` after evaluator raw (score-affecting; fail closed)."""
    graph = graph_for_lock(lock)
    try:
        return _run(score_postprocess(graph, value, ctx=ctx))
    except Exception:
        _LOG.exception("extension hook_score_postprocess failed")
        raise
