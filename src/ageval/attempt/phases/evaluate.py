"""evaluate phase: writers stop, gold arrives, evaluator decides.

Gold isolation here is a cut in *time*, not a mount trick: ``evaluation/`` is
uploaded at the start of this phase, so nothing the Agent could read ever had it
on disk. Isolated evaluate adds a cut in *space*: gold lands only on the second
Host. The verdict enters the Attempt exactly once, via ``bind_evaluation``.
The ``evaluation_runtime`` winner returns raw; it does not bind PASS.
"""

from __future__ import annotations

from pathlib import Path

from ageval.attempt.ctx import AttemptCtx
from ageval.attempt.emit import emit
from ageval.config.model import thaw
from ageval.environments.protocol import (
    ARTIFACTS_PATH,
    EVALUATION_PATH,
    WORKSPACE_PATH,
    EnvironmentProvider,
)
from ageval.evidence.store import TASK_ARTIFACTS_REL
from ageval.plugins.binding import bind_winner
from ageval.plugins.slots import AFTER_EVALUATE, BEFORE_EVALUATE, ENVIRONMENT, EVALUATION_RUNTIME

PHASE = "evaluate"
UNKNOWN_EVALUATE_ENVIRONMENT = "unknown_evaluate_environment"


async def run(ctx: AttemptCtx) -> None:
    ctx.phase = PHASE
    ctx.assert_writers_stopped()  # solver writers; Agent Service may still be up
    await emit(ctx, BEFORE_EVALUATE)
    if named_evaluate_environments(ctx):
        # Named hosts start on first exec / session(environment=), not here.
        pass
    else:
        await _ensure_evaluate_host(ctx)
        await _prepare_evaluate_runtime(ctx)
        await _materialize_on_host(ctx, ctx.scoring_host)
    impl = bind_winner(ctx.registry, ctx.bindings, EVALUATION_RUNTIME)
    plugin_id = ctx.bindings.winners[EVALUATION_RUNTIME].plugin_id
    ctx.services.register(EVALUATION_RUNTIME, impl, plugin_id=plugin_id)
    result = await impl.evaluate(ctx)
    ctx.bind_evaluation(result)
    # Post-processing may annotate metrics; it may not change the verdict.
    status_before = str((result or {}).get("status") or "")
    after = await emit(ctx, AFTER_EVALUATE, result)
    if isinstance(after, dict) and str(after.get("status") or "") != status_before:
        raise RuntimeError("after_evaluate must not change the evaluation status")


def named_evaluate_environments(ctx: AttemptCtx) -> dict[str, dict[str, str]]:
    lock = getattr(ctx, "lock", None)
    refs = thaw(getattr(lock, "resolved_references", None) or {})
    raw = refs.get("evaluation_environments") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for name, recipe in raw.items():
        if isinstance(name, str) and isinstance(recipe, dict):
            out[name] = {str(key): str(value) for key, value in recipe.items()}
    return out


async def ensure_named_host(ctx: AttemptCtx, name: str) -> EnvironmentProvider:
    """Start one named scoring host on first use. Unknown names do not start."""
    recipes = named_evaluate_environments(ctx)
    if name not in recipes:
        raise RuntimeError(UNKNOWN_EVALUATE_ENVIRONMENT)
    host = ctx.evaluate_hosts.get(name)
    if host is None:
        raise RuntimeError(UNKNOWN_EVALUATE_ENVIRONMENT)
    if name in ctx.started_evaluate_names:
        return host
    await host.preflight()
    await host.start(force_build=ctx.lock.force_build)
    ctx.started_evaluate_names.add(name)
    ctx.record_fact(
        "evaluate_host_started",
        {"name": name, "kind": getattr(host, "kind", "")},
    )
    await _materialize_on_host(ctx, host, name=name)
    return host


async def bind_named_environment(ctx: AttemptCtx, name: str) -> EnvironmentProvider:
    """Point the environment service at a named host for ACP attach_stdio."""
    host = await ensure_named_host(ctx, name)
    winner = ctx.bindings.winners.get(ENVIRONMENT)
    plugin_id = winner.plugin_id if winner is not None else getattr(host, "kind", "environment")
    ctx.services.register(ENVIRONMENT, host, plugin_id=plugin_id)
    await _prepare_named_runtime(ctx, name)
    return host


async def _ensure_evaluate_host(ctx: AttemptCtx) -> None:
    host = ctx.evaluate_host
    if host is None or host is ctx.host:
        return
    await host.preflight()
    await host.start(force_build=ctx.lock.force_build)
    ctx.record_fact("evaluate_host_started", {"kind": getattr(host, "kind", "")})
    winner = ctx.bindings.winners.get(ENVIRONMENT)
    plugin_id = winner.plugin_id if winner is not None else getattr(host, "kind", "environment")
    ctx.services.register(ENVIRONMENT, host, plugin_id=plugin_id)


async def _prepare_evaluate_runtime(ctx: AttemptCtx) -> None:
    """Probe/install ACP on the scoring host for profiles not used during run."""
    if ctx.evaluate_host is None or ctx.evaluate_host is ctx.host:
        return
    await _prepare_acp_profiles(ctx)


async def _prepare_named_runtime(ctx: AttemptCtx, name: str) -> None:
    await _prepare_acp_profiles(ctx, name=name)


async def _prepare_acp_profiles(ctx: AttemptCtx, name: str | None = None) -> None:
    parent = getattr(ctx.agent_service, "service", None) or ctx.agent_service
    binder = getattr(parent, "binder", None)
    if binder is None:
        return
    sealed = {str(item) for item in (getattr(parent, "_run_profile_ids", None) or ())}
    from ageval.attempt.emit import run_chain
    from ageval.plugins.slots import AFTER_ENVIRONMENT_READY

    for row in thaw(getattr(ctx.lock, "agent_profiles", None) or ()):
        if not isinstance(row, dict):
            continue
        profile_id = str(row.get("id") or "")
        if not profile_id or profile_id in sealed:
            continue
        if str(row.get("executor") or "") != "acp":
            continue
        await run_chain(binder.graph(profile_id), AFTER_ENVIRONMENT_READY, None, ctx=ctx)
        detail: dict[str, str] = {"profile_id": profile_id}
        if name:
            detail["name"] = name
        ctx.record_fact("evaluate_runtime_prepared", detail)


async def _materialize_on_host(
    ctx: AttemptCtx,
    host: EnvironmentProvider,
    *,
    name: str | None = None,
) -> None:
    """Copy harvested artifacts, workspace trees, and gold onto one scoring host."""
    staged = ctx.evidence.path(TASK_ARTIFACTS_REL)
    extra = {"name": name} if name else {}
    if staged.is_dir() and any(staged.iterdir()):
        await host.upload(staged, ARTIFACTS_PATH)
        ctx.record_fact("artifacts_materialized", {"at": PHASE, **extra})
    for snapshot in _workspace_tree_snapshots(ctx, staged):
        await host.upload(snapshot, WORKSPACE_PATH)
        ctx.record_fact(
            "workspace_materialized",
            {"at": PHASE, "artifact": snapshot.name, **extra},
        )
    if ctx.evaluation_src is not None and ctx.evaluation_src.is_dir():
        await host.upload(ctx.evaluation_src, EVALUATION_PATH)
        ctx.record_fact("gold_materialized", {"at": PHASE, **extra})


def _workspace_tree_snapshots(ctx: AttemptCtx, staged: Path) -> list[Path]:
    lock = getattr(ctx, "lock", None)
    if lock is None:
        return []
    refs = thaw(getattr(lock, "resolved_references", None) or {})
    artifacts = {
        str(row.get("id")): row
        for row in (refs.get("artifacts") or [])
        if isinstance(row, dict) and row.get("id")
    }
    out: list[Path] = []
    for inp in refs.get("evaluation_inputs") or []:
        if not isinstance(inp, dict):
            continue
        if str(inp.get("target") or "") != "workspace":
            continue
        aid = str(inp.get("artifact") or "")
        row = artifacts.get(aid) or {}
        if str(row.get("kind") or "") != "tree":
            continue
        snapshot = staged / aid
        if snapshot.is_dir():
            out.append(snapshot)
    return out
