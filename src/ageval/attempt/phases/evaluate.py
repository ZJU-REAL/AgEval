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
from ageval.environments.protocol import ARTIFACTS_PATH, EVALUATION_PATH, WORKSPACE_PATH
from ageval.evidence.store import TASK_ARTIFACTS_REL
from ageval.plugins.binding import bind_winner
from ageval.plugins.slots import AFTER_EVALUATE, BEFORE_EVALUATE, ENVIRONMENT, EVALUATION_RUNTIME

PHASE = "evaluate"


async def run(ctx: AttemptCtx) -> None:
    ctx.phase = PHASE
    ctx.assert_writers_stopped()  # solver writers; Agent Service may still be up
    await emit(ctx, BEFORE_EVALUATE)
    await _ensure_evaluate_host(ctx)
    await _upload_task_artifacts(ctx)
    host = ctx.scoring_host
    if ctx.evaluation_src is not None and ctx.evaluation_src.is_dir():
        await host.upload(ctx.evaluation_src, EVALUATION_PATH)
        ctx.record_fact("gold_materialized", {"at": PHASE})
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


async def _upload_task_artifacts(ctx: AttemptCtx) -> None:
    """The task published on this side; the evaluator judges inside the scoring box."""
    staged = ctx.evidence.path(TASK_ARTIFACTS_REL)
    host = ctx.scoring_host
    if staged.is_dir() and any(staged.iterdir()):
        await host.upload(staged, ARTIFACTS_PATH)
        ctx.record_fact("artifacts_materialized", {"at": PHASE})
    for snapshot in _workspace_tree_snapshots(ctx, staged):
        await host.upload(snapshot, WORKSPACE_PATH)
        ctx.record_fact(
            "workspace_materialized",
            {"at": PHASE, "artifact": snapshot.name},
        )


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
