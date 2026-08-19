"""Public ``ageval run`` use case: mint identity, build the ctx, run the Attempt.

This module assembles one Attempt and maps its outcome to an exit code. It owns
no orchestration: the phase order lives in ``ageval.attempt``.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ageval.attempt import run_attempt as run_attempt_pipeline
from ageval.attempt.ctx import AttemptCtx
from ageval.config.constants import (
    ENVIRONMENT_DIR,
    EVALUATION_DIR,
    SEED_DIR,
)
from ageval.config.model import LockedTaskConfig, locked_to_summary, thaw
from ageval.evaluation.bind import AttemptResult, bind_result
from ageval.evidence.locators import default_runs_root
from ageval.evidence.store import AttemptEvidenceStore
from ageval.plugins.protocol import ExtensionGraph
from ageval.plugins.services import ServiceTable
from ageval.plugins.slots import ENVIRONMENT, EXECUTOR
from ageval.runtime.cancellation import CancellationSignal
from ageval.runtime.identity import IdentityFactory

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ERROR = 2


async def run_attempt(
    dataset: Path | str,
    task: str,
    *,
    profile: str | None = None,
    profiles_path: Path | str | None = None,
    overrides: dict[str, Any] | None = None,
    keep_workspace: bool = False,
    force_build: bool = False,
    identity_factory: IdentityFactory | None = None,
) -> tuple[int, AttemptResult]:
    """Run one foreground Attempt and return its exit code and result."""
    from ageval.application.composition import build_lock_command

    locked = build_lock_command().lock(
        dataset,
        task,
        profile=profile,
        profiles_path=profiles_path,
        overrides=overrides,
        force_build=force_build,
    )
    lock = locked.lock
    dataset_root = locked.resolved.dataset_root
    task_root = locked.resolved.task_dir

    factory = identity_factory or IdentityFactory()
    run_ident = factory.new_run()
    trial_ident = factory.new_trial(run_ident, lock.digest)
    attempt_ident = factory.new_attempt(trial_ident)

    evidence = _open_evidence(
        dataset_root=dataset_root,
        lock=lock,
        run_id=run_ident.value,
        attempt_id=attempt_ident.value,
    )
    evidence.write_lock_summary(locked.summary())

    profile_id, graph = _selected_profile(lock)
    services = ServiceTable()
    host = _bind_environment(graph, services, attempt_root=evidence.path("box"))
    executor_winner = graph.winners.get(EXECUTOR)
    if executor_winner is not None:
        services.register(EXECUTOR, executor_winner.impl, plugin_id=executor_winner.plugin_id)

    await host.preflight()

    ctx = AttemptCtx(
        run_id=run_ident.value,
        trial_id=trial_ident.value,
        attempt_id=attempt_ident.value,
        lock=lock,
        profile_id=profile_id,
        bindings=graph,
        services=services,
        host=host,
        evidence=evidence,
        cancellation=CancellationSignal(),
        task_root=task_root,
        dataset_root=dataset_root,
        seed_dir=_optional_dir(task_root, lock, "seed_dir", SEED_DIR),
        environment_src=_optional_dir(task_root, lock, "environment_dir", ENVIRONMENT_DIR),
        evaluation_src=_optional_dir(task_root, lock, "evaluation_dir", EVALUATION_DIR),
        deadline_monotonic=_deadline(lock),
        keep_workspace=keep_workspace,
    )

    error_phase: str | None = None
    try:
        await run_attempt_pipeline(ctx)
    except Exception as exc:  # noqa: BLE001 — the phase name is the operator's answer
        error_phase = ctx.phase
        ctx.record_fact(
            "phase_failed", {"phase": ctx.phase, "error": f"{type(exc).__name__}: {exc}"}
        )

    result = bind_result(
        evaluator_raw=ctx.evaluation_result,
        kind=host.kind,
        capabilities_used=sorted(host.capabilities.names()),
        agent_invocations=len(evidence.list_invocations()),
        evidence_path=evidence.locator,
        cleanup_warning=_cleanup_warning(ctx),
        error_phase=error_phase,
        facts=tuple(ctx.facts_as_list()),
    )
    evidence.write_summary({"result": result.as_dict(), "facts": ctx.facts_as_list()})
    _write_result(evidence, result)
    return _exit_code(result), result


def _open_evidence(
    *,
    dataset_root: Path,
    lock: LockedTaskConfig,
    run_id: str,
    attempt_id: str,
) -> AttemptEvidenceStore:
    runs_root = default_runs_root(dataset_root)
    runs_root.mkdir(parents=True, exist_ok=True)
    run_dir = runs_root / f"{lock.digest.replace(':', '_')[:48]}_{run_id[:16]}"
    return AttemptEvidenceStore(
        root=run_dir,
        attempt_id=attempt_id,
        run_id=run_id,
        dataset_root=dataset_root,
    )


def _selected_profile(lock: LockedTaskConfig) -> tuple[str, ExtensionGraph]:
    """Re-resolve the locked graph for this run (same registry, same bindings)."""
    from ageval.plugins.bootstrap import ensure_bootstrapped
    from ageval.plugins.protocol import intent_from_profile
    from ageval.plugins.resolve import resolve

    rows = list(lock.agent_profiles)
    if not rows:
        raise RuntimeError("task declares no agent profile role slot to run")
    profile = rows[0]
    profile_id = str(profile.get("id"))
    intent = intent_from_profile(
        profile,
        environment=lock.environment,
        requires=thaw(lock.requires),
    )
    intent.profile_id = profile_id
    return profile_id, resolve(intent, ensure_bootstrapped(), materialize=True)


def _bind_environment(graph: ExtensionGraph, services: ServiceTable, *, attempt_root: Path) -> Any:
    """Materialize the box winner with the engine-owned work root."""
    from ageval.plugins.bootstrap import ensure_bootstrapped
    from ageval.plugins.registry import Registration

    winner = graph.winners.get(ENVIRONMENT)
    if winner is None:
        raise RuntimeError("no environment kind is bound for this Attempt")
    registration = ensure_bootstrapped().get_registration(ENVIRONMENT, winner.plugin_id)
    if isinstance(registration, Registration) and registration.is_factory:
        host = registration.impl(
            options=dict(winner.options or {}),
            attempt_root=str(attempt_root),
            plugin_id=winner.plugin_id,
        )
    else:
        host = winner.impl
    services.register(ENVIRONMENT, host, plugin_id=winner.plugin_id)
    return host


def _optional_dir(task_root: Path, lock: LockedTaskConfig, ref: str, fallback: str) -> Path | None:
    refs = thaw(lock.resolved_references)
    rel = refs.get(ref) or fallback
    candidate = task_root / str(rel)
    return candidate if candidate.is_dir() else None


def _deadline(lock: LockedTaskConfig) -> float | None:
    wall = thaw(lock.limits).get("wall_time_seconds")
    if not isinstance(wall, int) or wall <= 0:
        return None
    return time.monotonic() + float(wall)


def _cleanup_warning(ctx: AttemptCtx) -> str | None:
    for fact in reversed(ctx.phase_facts):
        if fact.name == "cleanup_warning":
            return str(fact.detail.get("error") or "cleanup failed")
    return None


def _write_result(evidence: AttemptEvidenceStore, result: AttemptResult) -> None:
    from ageval.evidence.attempt_record import write_attempt_result

    write_attempt_result(evidence.root, result.as_dict())


def _exit_code(result: AttemptResult) -> int:
    if result.status == "PASS":
        return EXIT_PASS
    if result.status == "FAIL":
        return EXIT_FAIL
    return EXIT_ERROR


def lock_summary_json(lock: LockedTaskConfig) -> dict[str, Any]:
    """Helper for callers that print the lock alongside the result."""
    return locked_to_summary(lock).as_dict()
