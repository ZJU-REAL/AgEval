"""Production ``ageval run`` use case — lock, mint identity, select stage adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ageval.adapters.package_fs import LocalPackageReader
from ageval.application.attempt.attempt_stages import (
    AttemptStageContext,
    DockerL1Stages,
    LocalL0Stages,
)
from ageval.application.attempt.phase_timing import PhaseTimer
from ageval.application.attempt.run_lifecycle import run_lifecycle
from ageval.config.capabilities import DeclarationCapabilityCatalog
from ageval.config.errors import ConfigError
from ageval.config.load_and_lock import ConfigCore
from ageval.config.model import thaw
from ageval.evaluation.result_binding import FlatResult
from ageval.evidence.locators import portable_run_locator
from ageval.runtime.identity import IdentityFactory


async def run_task(
    package_root: Path,
    task_id: str,
    *,
    evidence_root: Path | None = None,
    allow_offline_agent: bool = False,
    keep_workspace: bool = False,
    overrides: dict[str, Any] | None = None,
    profiles_path: Path | str | None = None,
    profile_bindings: dict[str, dict[str, Any]] | None = None,
    identity_factory: IdentityFactory | None = None,
) -> tuple[int, FlatResult, dict[str, Any]]:
    """Run one foreground Attempt and return (exit_code, result, details).

    *package_root* is the **Database** root (``ageval.dataset/1``). Member
    ``task.yaml`` is resolved via ``resolve_task``; the task directory is the
    package root for harness/evaluator relative paths.
    """
    from ageval.config.database import resolve_task
    from ageval.registry.resolve import resolve_database_root
    from ageval.runtime.task_import_isolation import clear_imports_from_task_dir

    database_root = resolve_database_root(package_root)
    resolved = resolve_task(database_root, task_id)
    package_root = resolved.task_dir

    try:
        return await _run_task_body(
            package_root=package_root,
            resolved=resolved,
            task_id=task_id,
            evidence_root=evidence_root,
            allow_offline_agent=allow_offline_agent,
            keep_workspace=keep_workspace,
            overrides=overrides,
            profiles_path=profiles_path,
            profile_bindings=profile_bindings,
            identity_factory=identity_factory,
        )
    finally:
        clear_imports_from_task_dir(package_root)


async def _run_task_body(
    *,
    package_root: Path,
    resolved: Any,
    task_id: str,
    evidence_root: Path | None,
    allow_offline_agent: bool,
    keep_workspace: bool,
    overrides: dict[str, Any] | None,
    profiles_path: Path | str | None,
    profile_bindings: dict[str, dict[str, Any]] | None,
    identity_factory: IdentityFactory | None,
) -> tuple[int, FlatResult, dict[str, Any]]:
    """Body of ``run_task`` after task_dir resolve (import cleanup wraps caller)."""
    from ageval.application.attempt.env_bootstrap import load_host_env_files
    from ageval.config.database import load_database_manifest
    from ageval.config.profiles import resolve_profile_bindings

    man = load_database_manifest(resolved.database_root)
    # Host credential locators from .env (values never enter lock/evidence).
    # Database-root .env only (#59 G4) — no default per-task .env auto-load.
    load_host_env_files(package_root=resolved.database_root)
    config = ConfigCore(package_reader=LocalPackageReader())
    bindings = profile_bindings
    if bindings is None:
        bindings = resolve_profile_bindings(resolved.database_root, profiles_path=profiles_path)
    try:
        lock = config.load_and_lock(
            package_root,
            task_id,
            overrides=overrides,
            capabilities=DeclarationCapabilityCatalog(),
            database_provenance=man.provenance,
            profile_bindings=bindings or None,
        )
    except ConfigError:
        # unknown task etc. before Attempt/evidence
        raise

    # Evidence defaults under Database root so operators inspect one tree per suite.
    db_root = Path(resolved.database_root)
    if evidence_root is None:
        from ageval.evidence.locators import default_runs_root

        evidence_root = default_runs_root(db_root)
    evidence_root = evidence_root.resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    # One Run/Trial/Attempt identity for this invocation — directory, evidence,
    # Agent Service, harness, and stages all reuse this chain.
    factory = identity_factory or IdentityFactory()
    run_ident = factory.new_run()
    trial_ident = factory.new_trial(run_ident, lock.digest)
    attempt_ident = factory.new_attempt(trial_ident)
    run_id = run_ident.value
    run_dir = evidence_root / f"{lock.digest.replace(':', '_')[:48]}_{run_id[:16]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    agent_file = package_root / ".ageval_agent_result.json"
    if agent_file.exists():
        agent_file.unlink()

    provider_cfg = thaw(lock.provider)
    provider_kind = str(provider_cfg.get("kind") or "local")
    agent_meta: dict[str, Any] = {
        "attempt_id": attempt_ident.value,
        "trial_id": trial_ident.value,
        "run_id": run_ident.value,
    }
    ctx = AttemptStageContext(
        package_root=package_root,
        lock=lock,
        run_dir=run_dir,
        agent_meta=agent_meta,
        allow_offline_agent=allow_offline_agent,
        keep_workspace=keep_workspace,
        attempt=attempt_ident,
        database_root=db_root,
        task_id=task_id,
        timer=PhaseTimer(),
    )
    stages: LocalL0Stages | DockerL1Stages = (
        DockerL1Stages(ctx=ctx) if provider_kind == "docker" else LocalL0Stages(ctx=ctx)
    )
    await run_lifecycle(lock, stages, attempt=attempt_ident)
    return _result_from_stage_ctx(ctx, database_root=db_root)


def _result_from_stage_ctx(
    ctx: AttemptStageContext, *, database_root: Path
) -> tuple[int, FlatResult, dict[str, Any]]:
    """Read the stage bag after Coordinator teardown."""
    result_doc = ctx.result_doc
    locator = portable_run_locator(ctx.run_dir, database_root=database_root)
    if not result_doc:
        result_doc = {
            "status": "ERROR",
            "error": {"kind": ctx.error_message or "attempt_incomplete"},
            "evidence_path": locator,
            "logs": locator,
        }
        ctx.result_doc = result_doc
        ctx.exit_code = 2
    score_raw = result_doc.get("score")
    score_f = float(score_raw) if isinstance(score_raw, int | float) else None
    metrics_raw = result_doc.get("metrics") if isinstance(result_doc.get("metrics"), dict) else {}
    err = result_doc.get("error") if isinstance(result_doc.get("error"), dict) else None
    flat = FlatResult(
        status=str(result_doc.get("status") or "ERROR"),
        score=score_f,
        metrics=metrics_raw or {},
        error_phase=(err or {}).get("phase") if err else None,
        cleanup_warning=result_doc.get("cleanup_warning"),  # type: ignore[arg-type]
        evidence_path=str(result_doc.get("evidence_path") or locator),
        runtime_kind=str(result_doc.get("runtime_kind") or "local_l0"),
        harness_kind=str(result_doc.get("harness_kind") or ctx.harness_kind or "failed"),
        agent_invocations=int(result_doc.get("agent_invocations") or ctx.inv_count),
        assurance=str(result_doc.get("assurance") or "l0"),
        logs=str(result_doc.get("logs") or locator),
    )
    details = {
        **ctx.details,
        "logs": flat.logs,
        "phase_timing": result_doc.get("phase_timing"),
        "digest": getattr(ctx.lock, "digest", None),
    }
    return ctx.exit_code, flat, details
