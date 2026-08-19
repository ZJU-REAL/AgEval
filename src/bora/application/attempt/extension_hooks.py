"""Wire L0–L5 extension multi-slots around production control points.

Merges multi-slot chains across every agent profile graph (same unique-keying
as image_contribute bake). Provide slots stay per-profile / per-session.
Prepare/env/score-related failures fail closed when requested; observational
hooks may continue after recording errors.

#71: env/eval hooks await registered callables (SPI). No declaration-DSL
collectors that Core later interprets as free-form command rows.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bora.config.model import LockedTaskConfig, thaw
from bora.config.overlay_files import overlay_root_for_binding
from bora.config.profiles import acp_entry_from_binding
from bora.plugins.bootstrap import ensure_bootstrapped
from bora.plugins.defaults.home_overlay import PLUGIN_ID as DEFAULT_PLUGIN_ID
from bora.plugins.defaults.home_overlay import default_home_overlay
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
from bora.plugins.middleware import run_handlers
from bora.plugins.protocol import BindingIntent, ExtensionGraph, intent_from_profile
from bora.plugins.resolve import resolve
from bora.plugins.slots import HOME_OVERLAY

_LOG = logging.getLogger(__name__)


def graph_for_lock(lock: LockedTaskConfig) -> ExtensionGraph:
    """Merge multi-slot chains from every profile; no first-profile-wins."""
    reg = ensure_bootstrapped()
    profiles = thaw(lock.agent_profiles) if lock.agent_profiles else []
    graphs: list[ExtensionGraph] = []
    if isinstance(profiles, list):
        for row in profiles:
            if not isinstance(row, dict):
                continue
            intent = intent_from_profile(row)
            if not intent.profile_id:
                intent.profile_id = str(row.get("id") or "default")
            graphs.append(resolve(intent, reg, materialize=False))
    if not graphs:
        return resolve(BindingIntent(profile_id="_lifecycle"), reg, materialize=False)
    if len(graphs) == 1:
        return graphs[0]
    merged = ExtensionGraph(profile_id="_merged")
    seen: set[tuple[str, str, int, str]] = set()
    for graph in graphs:
        for slot, handlers in graph.chains.items():
            dest = merged.chains.setdefault(slot, [])
            for handler in handlers:
                key = (slot, handler.plugin_id, handler.priority, handler.source)
                if key in seen:
                    continue
                seen.add(key)
                dest.append(handler)
    return merged


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


def _per_profile_graphs(lock: LockedTaskConfig, *, materialize: bool) -> list[ExtensionGraph]:
    reg = ensure_bootstrapped()
    profiles = thaw(lock.agent_profiles) if lock.agent_profiles else []
    graphs: list[ExtensionGraph] = []
    if isinstance(profiles, list):
        for row in profiles:
            if not isinstance(row, dict):
                continue
            intent = intent_from_profile(row)
            if not intent.profile_id:
                intent.profile_id = str(row.get("id") or "default")
            graphs.append(resolve(intent, reg, materialize=materialize))
    return graphs


def acp_entries_from_lock(lock: LockedTaskConfig) -> list[str]:
    """Unique ACP ``options.entry`` values on this lock (job overlay + profiles)."""
    seen: list[str] = []

    def add(binding: Mapping[str, Any]) -> None:
        entry = acp_entry_from_binding(binding)
        if entry and entry not in seen:
            seen.append(entry)

    overlay = thaw(lock.job_overlay) or {}
    bindings = overlay.get("bindings") if isinstance(overlay, Mapping) else None
    if isinstance(bindings, Mapping):
        for row in bindings.values():
            if isinstance(row, Mapping):
                add(row)
    profiles = thaw(lock.agent_profiles) if lock.agent_profiles else []
    if isinstance(profiles, list):
        for row in profiles:
            if isinstance(row, Mapping):
                add(row)
    return seen


def _profile_rows(lock: LockedTaskConfig) -> list[Mapping[str, Any]]:
    profiles = thaw(lock.agent_profiles) if lock.agent_profiles else []
    if not isinstance(profiles, list):
        return []
    return [row for row in profiles if isinstance(row, Mapping)]


async def _run_per_profile_home_overlay(
    lock: LockedTaskConfig,
    value: Any,
    *,
    ctx: Any,
) -> Any:
    """Run each profile's home_overlay chain with that profile's overlay root.

    ``agent_ref`` bindings resolve ``src`` against the installed Agent package.
    Hand-written profiles keep the Database root. Copy still lands in the
    Attempt home_overlay dest — never the Dataset tree or the agents cache.
    """
    payload = dict(value) if isinstance(value, dict) else {}
    default_raw = payload.get("package_root")
    default_root = Path(str(default_raw)) if default_raw else None
    current: Any = payload
    for row in _profile_rows(lock):
        intent = intent_from_profile(row)
        if not intent.profile_id:
            intent.profile_id = str(row.get("id") or "default")
        graph = resolve(intent, ensure_bootstrapped(), materialize=True)
        handlers = [
            href for href in graph.chain(HOME_OVERLAY) if href.plugin_id != DEFAULT_PLUGIN_ID
        ]
        if not handlers:
            continue
        profile_payload = dict(current) if isinstance(current, dict) else dict(payload)
        root = overlay_root_for_binding(row, default_root)
        if root is not None:
            profile_payload["package_root"] = str(root)
        entry = acp_entry_from_binding(row)
        if entry:
            profile_payload["acp_entries"] = [entry]
        result = await run_handlers(handlers, profile_payload, ctx=ctx)
        current = result if isinstance(result, dict) else profile_payload
    return current


def hook_home_overlay(
    lock: LockedTaskConfig,
    value: Any = None,
    *,
    ctx: Any = None,
    fail_closed: bool = True,
) -> Any:
    """Emit home_overlay: Core default wraps per-profile plugin handlers."""

    async def _emit() -> Any:
        payload = dict(value) if isinstance(value, dict) else {}
        payload["acp_entries"] = acp_entries_from_lock(lock)

        async def nxt(v: Any) -> Any:
            return await _run_per_profile_home_overlay(lock, v, ctx=ctx)

        return await default_home_overlay(ctx, payload, nxt)

    try:
        return _run(_emit())
    except Exception:
        if fail_closed:
            raise
        _LOG.exception("extension hook_home_overlay failed (fail-open)")
        return value


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
