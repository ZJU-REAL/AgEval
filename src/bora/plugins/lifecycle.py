"""Lifecycle emit helpers for L0–L5 multi/provide slots.

Application / Agent Service call these at real control points (not collect-only).
Host awaits registered callables — plugins rewrite/short-circuit; no declaration DSL.
"""

from __future__ import annotations

from typing import Any

from bora.plugins.middleware import run_chain
from bora.plugins.protocol import ExtensionGraph
from bora.plugins.slots import (
    AFTER_AGENT_CLOSE,
    AFTER_AGENT_OPEN,
    AFTER_CLEANUP,
    AFTER_EVALUATE,
    AFTER_PREPARE,
    AFTER_RUN,
    BEFORE_AGENT_CLOSE,
    BEFORE_AGENT_OPEN,
    BEFORE_CLEANUP,
    BEFORE_EVALUATE,
    BEFORE_PREPARE,
    BEFORE_RUN,
    CLEANUP_ACTIONS,
    CLEANUP_REPORT,
    ENV_ACTION,
    ENV_INJECT,
    ENV_PREPARE_COMMANDS,
    ENV_TEARDOWN_COMMANDS,
    EVALUATION_INPUT_CONTRIBUTE,
    EVALUATION_RUNTIME,
    EVIDENCE_EXTRA,
    IMAGE_CONTRIBUTE,
    NORMALIZE_AGENT_RESULT,
    SCORE_POSTPROCESS,
    TRAJECTORY_COLLECT,
    TRAJECTORY_ENRICH,
    TRAJECTORY_SEAL,
)


async def emit_phase(
    graph: ExtensionGraph,
    *,
    before_slot: str,
    after_slot: str,
    value: Any = None,
    ctx: Any = None,
) -> Any:
    mid = await run_chain(graph, before_slot, value, ctx=ctx)
    return await run_chain(graph, after_slot, mid, ctx=ctx)


async def emit_prepare(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    return await emit_phase(
        graph, before_slot=BEFORE_PREPARE, after_slot=AFTER_PREPARE, value=value, ctx=ctx
    )


async def emit_run(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    return await emit_phase(
        graph, before_slot=BEFORE_RUN, after_slot=AFTER_RUN, value=value, ctx=ctx
    )


async def emit_evaluate(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    return await emit_phase(
        graph, before_slot=BEFORE_EVALUATE, after_slot=AFTER_EVALUATE, value=value, ctx=ctx
    )


async def emit_cleanup(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """Cleanup bookends + cleanup_actions/report (must not revoke score)."""
    mid = await emit_phase(
        graph, before_slot=BEFORE_CLEANUP, after_slot=AFTER_CLEANUP, value=value, ctx=ctx
    )
    mid = await run_chain(graph, CLEANUP_ACTIONS, mid, ctx=ctx)
    return await run_chain(graph, CLEANUP_REPORT, mid, ctx=ctx)


async def collect_image_contribute(
    graph: ExtensionGraph,
    *,
    ctx: Any = None,
) -> list[Any]:
    seed: list[Any] = []
    result = await run_chain(graph, IMAGE_CONTRIBUTE, seed, ctx=ctx)
    if isinstance(result, list):
        return result
    if result is None:
        return []
    return [result]


# --- L2: agent session bookends (#71 A) ---


async def emit_agent_open(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """before_agent_open → after_agent_open (fail closed at host)."""
    return await emit_phase(
        graph, before_slot=BEFORE_AGENT_OPEN, after_slot=AFTER_AGENT_OPEN, value=value, ctx=ctx
    )


async def emit_agent_close(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """before_agent_close → after_agent_close (host may fail-open around close)."""
    return await emit_phase(
        graph, before_slot=BEFORE_AGENT_CLOSE, after_slot=AFTER_AGENT_CLOSE, value=value, ctx=ctx
    )


async def normalize_agent_result(
    graph: ExtensionGraph, value: Any = None, *, ctx: Any = None
) -> Any:
    """Multi-slot normalize_agent_result after invoke bookends."""
    return await run_chain(graph, NORMALIZE_AGENT_RESULT, value, ctx=ctx)


# --- L4: trajectory / evidence (#71 B) ---


async def collect_trajectory(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """Multi-slot trajectory_collect — payload is live write source, not a dict DSL."""
    return await run_chain(graph, TRAJECTORY_COLLECT, value, ctx=ctx)


async def enrich_trajectory(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """Multi-slot trajectory_enrich before durable write."""
    return await run_chain(graph, TRAJECTORY_ENRICH, value, ctx=ctx)


async def call_trajectory_seal(
    graph: ExtensionGraph, value: Any = None, *, ctx: Any = None
) -> Any:
    """Single-winner trajectory_seal provide (authority-shape marker / extra fields)."""
    pref = graph.providers.get(TRAJECTORY_SEAL)
    if pref is None:
        return value
    impl = pref.impl
    if callable(impl):
        result = impl(value=value, ctx=ctx)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[misc]
        if isinstance(result, dict) and isinstance(value, dict):
            out = dict(value)
            out["seal_marker"] = result
            return out
        return result if result is not None else value
    if isinstance(impl, dict) and isinstance(value, dict):
        out = dict(value)
        out["seal_marker"] = dict(impl)
        return out
    return value


async def collect_evidence_extra(
    graph: ExtensionGraph, value: Any = None, *, ctx: Any = None
) -> Any:
    """Multi-slot evidence_extra (list of extra evidence records)."""
    seed: list[Any] = list(value) if isinstance(value, list) else ([] if value is None else [value])
    return await run_chain(graph, EVIDENCE_EXTRA, seed, ctx=ctx)


# --- L1: env lifecycle SPI (#71 C) — executable middleware, not command rows ---


async def emit_env_prepare(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """Multi env_prepare_commands: handlers do real work / rewrite env handoff."""
    return await run_chain(graph, ENV_PREPARE_COMMANDS, value, ctx=ctx)


async def emit_env_inject(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """Multi env_inject: rewrite env handoff object (no host DSL interpreter)."""
    return await run_chain(graph, ENV_INJECT, value, ctx=ctx)


async def emit_env_teardown(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """Multi env_teardown_commands before resource close."""
    return await run_chain(graph, ENV_TEARDOWN_COMMANDS, value, ctx=ctx)


async def call_env_action(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """Single-winner env_action provide SPI (gate / policy object)."""
    pref = graph.providers.get(ENV_ACTION)
    if pref is None:
        return value
    impl = pref.impl
    if callable(impl):
        # Factory already materialized: call SPI methods or factory-returned object.
        if hasattr(impl, "check") and callable(impl.check):
            result = impl.check(value, ctx=ctx)
            if hasattr(result, "__await__"):
                return await result  # type: ignore[misc]
            return result
        result = impl(value=value, ctx=ctx) if _accepts_kwargs(impl) else impl()
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[misc]
        return result
    return impl


def _accepts_kwargs(fn: Any) -> bool:
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    for p in sig.parameters.values():
        if p.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
            return True
        if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD and p.name in {
            "value",
            "ctx",
            "kwargs",
        }:
            return True
    # Zero-arg factory / marker
    return len(sig.parameters) == 0


# --- L3: evaluation adjacency (#71 D) ---


async def collect_evaluation_input(
    graph: ExtensionGraph, value: Any = None, *, ctx: Any = None
) -> Any:
    """Multi evaluation_input_contribute (score-affecting; host fail closed)."""
    return await run_chain(graph, EVALUATION_INPUT_CONTRIBUTE, value, ctx=ctx)


async def call_evaluation_runtime(
    graph: ExtensionGraph, value: Any = None, *, ctx: Any = None
) -> Any:
    """Single-winner evaluation_runtime provide (lock-visible annotation)."""
    pref = graph.providers.get(EVALUATION_RUNTIME)
    if pref is None:
        return value
    impl = pref.impl
    if callable(impl):
        result = impl(value=value, ctx=ctx) if _accepts_kwargs(impl) else impl()
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[misc]
        return result
    return impl


async def score_postprocess(graph: ExtensionGraph, value: Any = None, *, ctx: Any = None) -> Any:
    """Multi score_postprocess after evaluator raw (score-affecting; fail closed)."""
    return await run_chain(graph, SCORE_POSTPROCESS, value, ctx=ctx)
