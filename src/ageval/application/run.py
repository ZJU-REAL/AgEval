"""Public ``ageval run`` use case: mint identity, build the ctx, run the Attempt.

This module assembles one Attempt and maps its outcome to an exit code. It owns
no orchestration: the phase order lives in ``ageval.attempt``.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from ageval.application.phase_timing import timing_from_facts
from ageval.attempt import run_attempt as run_attempt_pipeline
from ageval.attempt.ctx import AttemptCtx
from ageval.config.constants import (
    ENVIRONMENT_DIR,
    EVALUATION_DIR,
    SEED_DIR,
)
from ageval.config.model import LockedTaskConfig, locked_to_summary, thaw
from ageval.environments.protocol import BoxSpec
from ageval.evaluation.bind import AttemptResult, bind_result
from ageval.evidence.locators import default_runs_root
from ageval.evidence.store import AttemptEvidenceStore
from ageval.plugins.binding import bind_winner
from ageval.plugins.bootstrap import ensure_bootstrapped
from ageval.plugins.protocol import ExtensionGraph
from ageval.plugins.services import ServiceTable
from ageval.plugins.slots import ENVIRONMENT
from ageval.runtime.agent_binding import AgentBinder
from ageval.runtime.agent_service_protocol import AgentServiceServer
from ageval.runtime.cancellation import CancellationSignal
from ageval.runtime.identity import IdentityFactory
from ageval.runtime.parent_agent import ParentAgentService, resolve_invoke_timeout_seconds

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ERROR = 2


async def probe_attempt(
    dataset: Path | str,
    task: str,
    *,
    profile: str | None = None,
    profiles_path: Path | str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lock and preflight without opening a box or invoking an Agent.

    Answers "would this run here?" — the lock resolves, the winning box says
    whether it could open, and nothing is started either way.
    """
    from ageval.application.composition import build_lock_command

    locked = build_lock_command().lock(
        dataset,
        task,
        profile=profile,
        profiles_path=profiles_path,
        overrides=overrides,
    )
    lock = locked.lock
    registry = ensure_bootstrapped()
    binder = AgentBinder(
        profiles=tuple(lock.agent_profiles),
        services=ServiceTable(),
        registry=registry,
        environment=lock.environment,
        environment_options=_environment_options(lock),
        requires=thaw(lock.requires),
    )
    graph = binder.graph(_selected_profile_id(lock))
    host = bind_winner(
        registry,
        graph,
        ENVIRONMENT,
        spec=_box_spec(
            lock,
            task_root=locked.resolved.task_dir,
            attempt_root=Path(tempfile.mkdtemp(prefix="ageval-probe-")),
        ),
        plugin_layers=_plugin_image_layers(graph),
    )
    probe: dict[str, Any] = {
        "task_id": lock.task_id,
        "digest": lock.digest,
        "environment": lock.environment,
        "capabilities": sorted(host.capabilities.names()),
        "started": False,
    }
    try:
        await host.preflight()
    except Exception as exc:  # noqa: BLE001 — the reason is the answer
        probe["ready"] = False
        probe["error"] = f"{type(exc).__name__}: {exc}"
        return probe
    probe["ready"] = True
    return probe


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

    registry = ensure_bootstrapped()
    profile_id = _selected_profile_id(lock)
    services = ServiceTable()
    binder = AgentBinder(
        profiles=tuple(lock.agent_profiles),
        services=services,
        registry=registry,
        environment=lock.environment,
        environment_options=_environment_options(lock),
        requires=thaw(lock.requires),
    )
    graph = binder.graph(profile_id)
    deadline = _deadline(lock)
    # The service comes up first so the box can carry its socket in.
    agent_service = _agent_service(
        attempt_id=attempt_ident.value,
        binder=binder,
        lock=lock,
        evidence=evidence,
        deadline_monotonic=deadline,
    )
    host = bind_winner(
        registry,
        graph,
        ENVIRONMENT,
        spec=_box_spec(
            lock,
            task_root=task_root,
            attempt_root=evidence.path("box"),
        ),
        plugin_layers=_plugin_image_layers(graph),
    )
    services.register(ENVIRONMENT, host, plugin_id=graph.winners[ENVIRONMENT].plugin_id)
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
        agent_service=agent_service,
        deadline_monotonic=deadline,
        keep_workspace=keep_workspace,
    )

    try:
        await run_attempt_pipeline(ctx)
    finally:
        # The run phase stops it too; this is the guarantee for earlier failures.
        agent_service.stop()

    result = bind_result(
        evaluator_raw=ctx.evaluation_result,
        kind=host.kind,
        capabilities_used=sorted(host.capabilities.names()),
        agent_invocations=len(evidence.list_invocations()),
        evidence_path=evidence.locator,
        cleanup_warning=_fact_detail(ctx, "cleanup_warning", "error"),
        error_phase=_fact_detail(ctx, "phase_failed", "phase"),
        facts=tuple(ctx.facts_as_list()),
    )
    facts = ctx.facts_as_list()
    evidence.write_summary(
        {
            "result": result.as_dict(),
            "facts": facts,
            "phase_timing": timing_from_facts(facts),
        }
    )
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
    return AttemptEvidenceStore(
        root=runs_root / attempt_id,
        attempt_id=attempt_id,
        run_id=run_id,
        dataset_root=dataset_root,
    )


def _selected_profile_id(lock: LockedTaskConfig) -> str:
    """The role slot this Attempt runs, or "" for a task with no Agent at all.

    Extra roles open on demand, per session.
    """
    rows = list(lock.agent_profiles)
    if not rows:
        return ""
    active = thaw(lock.parameters).get("active_profile")
    if isinstance(active, str) and active.strip():
        return active.strip()
    return str(rows[0].get("id"))


def _plugin_image_layers(graph: ExtensionGraph) -> tuple[tuple[str, str, str, str], ...]:
    """Bake files the bound plugins declared, for kinds that build."""
    from ageval.plugins.image_layers import layers_for_plugins

    bound = {ref.plugin_id for ref in graph.winners.values()}
    for chain in graph.chains.values():
        bound.update(handler.plugin_id for handler in chain)
    return tuple(
        (layer.plugin_id, str(layer.dockerfile), str(layer.package_root), layer.body)
        for layer in layers_for_plugins(frozenset(bound))
    )


def _environment_options(lock: LockedTaskConfig) -> dict[str, Any]:
    """Job options the box kind reads (never the executor's own options)."""
    overlay = thaw(lock.job_overlay) if lock.job_overlay is not None else {}
    options = overlay.get("environment_options")
    return dict(options) if isinstance(options, dict) else {}


def _box_spec(
    lock: LockedTaskConfig,
    *,
    task_root: Path,
    attempt_root: Path,
) -> BoxSpec:
    """Engine context for the box: the work root plus whatever recipe shipped."""
    references = thaw(lock.resolved_references)
    return BoxSpec(
        attempt_root=attempt_root,
        task_root=task_root,
        repo_root=Path.cwd(),
        dockerfile=references.get("environment_dockerfile"),
        compose_file=references.get("environment_compose"),
    )


def _agent_service(
    *,
    attempt_id: str,
    binder: AgentBinder,
    lock: LockedTaskConfig,
    evidence: AttemptEvidenceStore,
    deadline_monotonic: float | None,
) -> AgentServiceServer:
    """Start the parent Agent Service the worker will call back into."""
    limits = thaw(lock.limits)
    parameters = thaw(lock.parameters)
    service = ParentAgentService(
        attempt_id=attempt_id,
        binder=binder,
        agent_invocation_limit=int(limits["agent_invocations"]),
        evidence_store=evidence,
        deadline_monotonic=deadline_monotonic,
        invoke_timeout_seconds=resolve_invoke_timeout_seconds(parameters),
    )
    # Short path: a Unix socket name has ~100 usable bytes, evidence roots do not.
    socket_dir = Path(tempfile.mkdtemp(prefix="ageval-"))
    server = AgentServiceServer(service, socket_dir / "agent.sock")
    server.start()
    return server


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


def _fact_detail(ctx: AttemptCtx, name: str, key: str) -> str | None:
    """Last recorded value of one fact detail, for the result document."""
    for fact in reversed(ctx.phase_facts):
        if fact.name == name:
            value = fact.detail.get(key)
            return str(value) if value else None
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
