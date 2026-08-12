"""Production ``bora run`` use case — Core 1–5 vertical slice (v0.6).

Helpers: evaluator worker · environment prepare (chore #31).
"""

from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path
from typing import Any

from bora.adapters.package_fs import LocalPackageReader
from bora.application.phase_timing import PhaseTimer, format_duration_ms
from bora.application.run_command_environment import prepare_postgresql_environment
from bora.application.run_command_evaluator import run_evaluator_worker
from bora.application.run_harness import run_harness_package
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw
from bora.evaluation.result_binding import FlatResult, bind_result
from bora.evidence.locators import portable_run_locator, seal_harness_for_evidence


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
) -> tuple[int, FlatResult, dict[str, Any]]:
    """Run one foreground Attempt and return (exit_code, result, details).

    *package_root* is the **Database** root (``bora.database/1``). Member
    ``task.yaml`` is resolved via ``resolve_task``; the task directory is the
    package root for harness/evaluator relative paths.
    """
    from bora.config.database import resolve_task
    from bora.registry.resolve import resolve_database_root
    from bora.runtime.task_import_isolation import clear_imports_from_task_dir

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
) -> tuple[int, FlatResult, dict[str, Any]]:
    """Body of ``run_task`` after task_dir resolve (import cleanup wraps caller)."""
    from bora.application.env_bootstrap import load_host_env_files
    from bora.config.database import load_database_manifest
    from bora.config.profiles import resolve_profile_bindings

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
    evidence_root = (evidence_root or (resolved.database_root / ".bora" / "runs")).resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    # Unique Run identity per invocation — never overwrite prior evidence by lock digest alone.
    from bora.evidence.store import AttemptEvidenceStore
    from bora.runtime.identity import IdentityFactory

    run_id = IdentityFactory().new_run().value
    run_dir = evidence_root / f"{lock.digest.replace(':', '_')[:48]}_{run_id[:16]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    agent_invocations = 0
    agent_meta: dict[str, Any] = {}
    assurance = "l0"
    l1_meta: dict[str, Any] = {}
    evidence_store: AttemptEvidenceStore | None = None
    timer = PhaseTimer()

    # Never trust residual agent materialization from a previous run/package tree.
    agent_file = package_root / ".bora_agent_result.json"
    if agent_file.exists():
        agent_file.unlink()

    # Parent Agent Service: non-empty agent_profiles ⇒ harness session/invoke (L0 only).
    import time as _time_mod

    _mono = _time_mod.monotonic
    prepare_t0 = _mono()
    profiles = thaw(lock.agent_profiles)
    params = thaw(lock.parameters)
    evaluation = thaw(lock.evaluation)
    provider_cfg = thaw(lock.provider)
    provider_kind = str(provider_cfg.get("kind") or "local")
    agent_profile = next((p for p in profiles if isinstance(p, dict)), None)
    # Issue #5: non-empty agent_profiles ⇒ Parent Agent Service (L0 only).
    # Docker/L1 owns its own SDK session path inside run_l1. No use_agent_session flag.
    agent_service = None
    agent_server = None
    agent_sock_path = None
    shared_attempt = None  # Runtime-owned Attempt shared with harness worker
    if agent_profile is not None and provider_kind != "docker":
        from bora.runtime.agent_service_protocol import AgentServiceServer

        limits = thaw(lock.limits) if hasattr(lock, "limits") else {}
        if not isinstance(limits, dict):
            limits = {}
        # limits may be mappingproxy from freeze
        try:
            inv_limit = int(thaw(lock.limits).get("agent_invocations") or 1)  # type: ignore[union-attr]
        except Exception:
            inv_limit = 1
        # One Runtime identity chain for Agent Service + harness worker (Attempt parent-owned).
        factory = IdentityFactory()
        run_ident = factory.new_run()
        trial_ident = factory.new_trial(run_ident, lock.digest)
        attempt_ident = factory.new_attempt(trial_ident)
        shared_attempt = attempt_ident
        evidence_store = AttemptEvidenceStore(
            root=run_dir,
            attempt_id=attempt_ident.value,
            run_id=run_ident.value,
            database_root=resolved.database_root,
        )
        # Lock summary without secrets (digest + profile ids only).
        with contextlib.suppress(Exception):
            from bora.adapters.executor_capabilities import get_capabilities

            profile_rows: list[dict[str, Any]] = []
            for p in profiles:
                if not isinstance(p, dict):
                    continue
                kind = str(p.get("executor") or "")
                cap = get_capabilities(kind)
                row: dict[str, Any] = {
                    "id": p.get("id"),
                    "executor": kind,
                    "model": p.get("model"),
                }
                opts = p.get("options")
                if isinstance(opts, dict) and opts.get("entry") is not None:
                    # Keep entry for fingerprint / actors_summary (#42/#59).
                    row["options"] = {"entry": opts.get("entry")}
                if p.get("base_url"):
                    row["base_url"] = p.get("base_url")
                if p.get("api_key"):
                    # Env locator name only — never secret values.
                    row["api_key"] = p.get("api_key")
                if cap is not None:
                    row["capabilities"] = {
                        "tools": cap.tools,
                        "structured_output": cap.structured_output,
                        "session": cap.session,
                        "stream": cap.stream,
                        "execution_mode": cap.execution_mode,
                    }
                profile_rows.append(row)
            lock_doc: dict[str, Any] = {
                "digest": lock.digest,
                "task_id": task_id,
                "profiles": profile_rows,
            }
            if lock.provenance is not None:
                lock_doc["provenance"] = thaw(lock.provenance)
            # #59 secret-free job binding for rehydrate / upload projection.
            if lock.job_overlay is not None:
                lock_doc["job_overlay"] = thaw(lock.job_overlay)
            evidence_store.write_lock_summary(lock_doc)
        # Wall hard ceiling from locked limits (design §13.1): pre-effect deadline.
        from bora.application.agent_service_assemble import (
            assemble_parent_agent_service,
            read_wall_deadline,
        )

        wall_s, deadline = read_wall_deadline(lock, monotonic_now=_mono())
        agent_service, invoke_timeout = assemble_parent_agent_service(
            profiles=profiles if isinstance(profiles, list) else [],
            package_root=package_root,
            attempt_id=attempt_ident.value,
            inv_limit=inv_limit,
            params=params if isinstance(params, dict) else {},
            evidence_store=evidence_store,
            deadline_monotonic=deadline,
        )
        agent_meta["wall_time_seconds"] = wall_s if wall_s > 0 else None
        agent_meta["deadline_armed"] = deadline is not None
        agent_meta["invoke_timeout_seconds"] = invoke_timeout
        # Unix socket path must stay short on macOS (~104 bytes).
        import tempfile

        short = Path(tempfile.gettempdir()) / f"bora-ags-{run_id[:12]}.sock"
        agent_sock_path = short
        agent_server = AgentServiceServer(agent_service, agent_sock_path)
        agent_server.start()
        agent_meta["attempt_id"] = attempt_ident.value
        agent_meta["trial_id"] = trial_ident.value
        agent_meta["run_id"] = run_ident.value

    if provider_kind == "docker":
        # Full L1 orchestration via LifecycleStages adapter (Spec 07).
        from bora.application.attempt_stages import AttemptStageContext, DockerL1Stages
        from bora.application.run_lifecycle import run_lifecycle

        # Env Manager before L1 when packages need postgresql + Docker agents (journeys).
        env_resource_docker = str(params.get("environment_resource") or "")
        if env_resource_docker == "postgresql":
            env_manager, evidence_store, env_meta, early = prepare_postgresql_environment(
                package_root=package_root,
                lock=lock,
                run_dir=run_dir,
                run_id=run_id,
                params=params if isinstance(params, dict) else {},
                agent_meta=agent_meta,
                evidence_store=evidence_store,
            )
            del env_manager  # L1 path does not hold env manager beyond prepare
            if early is not None:
                return early
            agent_meta["environment"] = env_meta
            (run_dir / "env_manager.json").write_text(
                json.dumps({"resource_id": env_meta.get("resource_id")}, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        stage_ctx = AttemptStageContext(
            package_root=package_root,
            lock=lock,
            run_dir=run_dir,
            agent_meta=agent_meta,
            allow_offline_agent=allow_offline_agent,
            keep_workspace=keep_workspace,
        )
        stages = DockerL1Stages(ctx=stage_ctx)
        await run_lifecycle(lock, stages)
        result_doc = stage_ctx.result_doc
        details = stage_ctx.details
        code = stage_ctx.exit_code
        score_raw = result_doc.get("score")
        score_f = float(score_raw) if isinstance(score_raw, int | float) else None
        metrics_raw = (
            result_doc.get("metrics") if isinstance(result_doc.get("metrics"), dict) else {}
        )
        err = result_doc.get("error") if isinstance(result_doc.get("error"), dict) else None
        flat = FlatResult(
            status=str(result_doc.get("status") or "ERROR"),
            score=score_f,
            metrics=metrics_raw or {},
            error_phase=(err or {}).get("phase") if err else None,
            cleanup_warning=result_doc.get("cleanup_warning"),  # type: ignore[arg-type]
            evidence_path=str(
                result_doc.get("evidence_path")
                or portable_run_locator(run_dir, database_root=resolved.database_root)
            ),
            runtime_kind=str(result_doc.get("runtime_kind") or "docker_l1"),
            harness_kind=str(result_doc.get("harness_kind") or "failed"),
            agent_invocations=int(result_doc.get("agent_invocations") or 0),
            assurance=str(result_doc.get("assurance") or "l0"),
            logs=str(
                result_doc.get("logs")
                or portable_run_locator(run_dir, database_root=resolved.database_root)
            ),
        )
        details = {
            **details,
            "logs": flat.logs,
            "phase_timing": result_doc.get("phase_timing"),
        }
        return code, flat, details

    # Environment Manager (Spec 09) — resource-type named only (postgresql).
    env_resource = str(params.get("environment_resource") or "")
    env_manager = None
    if env_resource == "postgresql":
        env_manager, evidence_store, env_meta, early = prepare_postgresql_environment(
            package_root=package_root,
            lock=lock,
            run_dir=run_dir,
            run_id=run_id,
            params=params if isinstance(params, dict) else {},
            agent_meta=agent_meta,
            evidence_store=evidence_store,
        )
        if early is not None:
            timer.add_ms("prepare", (_mono() - prepare_t0) * 1000.0)
            return early
        agent_meta["environment"] = env_meta
        (run_dir / "env_manager.json").write_text(
            json.dumps({"resource_id": env_meta.get("resource_id")}, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    timer.add_ms("prepare", (_mono() - prepare_t0) * 1000.0)
    from bora.application.extension_hooks import (
        hook_cleanup,
        hook_evaluate,
        hook_evaluation_input,
        hook_evaluation_runtime,
        hook_prepare,
        hook_run,
        hook_score_postprocess,
    )

    hook_prepare(lock)

    try:
        harness_timeout = (
            float(params.get("harness_timeout_seconds") or 300.0)
            if isinstance(params, dict)
            else 300.0
        )
        # Cap harness worker by locked wall_time when present (hard ceiling).
        try:
            wall_cap = float(thaw(lock.limits).get("wall_time_seconds") or 0)  # type: ignore[union-attr]
        except Exception:
            wall_cap = 0.0
        if wall_cap > 0:
            harness_timeout = min(harness_timeout, wall_cap)
        run_t0 = _mono()
        hook_run(lock)
        harness_out = await run_harness_package(
            lock,
            package_root,
            timeout_seconds=harness_timeout,
            agent_service_sock=str(agent_sock_path) if agent_sock_path else None,
            # Reuse ParentAgentService identity so AgentSession + harness share one Attempt.
            attempt=shared_attempt,
            database_root=resolved.database_root,
        )
        timer.add_ms("run", (_mono() - run_t0) * 1000.0)
    finally:
        if agent_server is not None:
            agent_server.stop()
        if agent_service is not None:
            agent_invocations = agent_service.invocations_completed
            agent_meta = {
                **agent_meta,
                "mode": "parent_agent_service",
                "invocations": agent_service.invocations_completed,
            }
        # Environment Manager teardown (env_teardown multi before close)
        if env_manager is not None:
            with contextlib.suppress(Exception):
                from types import SimpleNamespace

                from bora.application.extension_hooks import hook_env_teardown

                td_ctx = SimpleNamespace(
                    attempt_id=str(agent_meta.get("attempt_id") or run_id),
                    package_root=package_root,
                    workdir=package_root,
                    run_dir=run_dir,
                    env_manager=env_manager,
                    resource_id=(agent_meta.get("environment") or {}).get("resource_id"),
                )
                hook_env_teardown(
                    lock,
                    agent_meta.get("environment") or {"phase": "teardown"},
                    ctx=td_ctx,
                )
            with contextlib.suppress(Exception):
                env_manager.close()
        marker = run_dir / "env_container_name.txt"
        if marker.is_file():
            try:
                from bora.adapters.environment_postgres import PostgresEnvironment

                name = marker.read_text(encoding="utf-8").strip()
                PostgresEnvironment(container_name=name).stop()
            except Exception:
                pass
            with contextlib.suppress(OSError):
                marker.unlink()
        for handoff in (package_root / ".bora_env_result.json", run_dir / "env_manager.json"):
            if handoff.exists():
                with contextlib.suppress(OSError):
                    handoff.unlink()

    envelope = harness_out.get("envelope") or {}
    harness_kind = "failed"
    if envelope.get("ok") and envelope.get("terminal", {}).get("kind") == "completed":
        harness_kind = "completed"
    elif envelope.get("ok"):
        harness_kind = str(envelope.get("terminal", {}).get("kind", "unknown"))

    # Writer barrier: require published artifacts before evaluator.
    eval_t0 = _mono()
    hook_evaluate(lock)
    published = dict(envelope.get("published") or {})
    eval_inputs = list(evaluation.get("inputs") or [])
    staging = run_dir / "eval_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    artifacts_map: dict[str, str] = {}
    error_phase: str | None = None
    if harness_kind != "completed":
        error_phase = "harness"
    else:
        for item in eval_inputs:
            if not isinstance(item, dict):
                continue
            art = item.get("artifact")
            if not art:
                continue
            # published paths may be absolute files from worker
            src_raw = published.get(str(art))
            if not src_raw:
                error_phase = "evaluation_input"
                break
            src = Path(str(src_raw))
            if not src.is_file():
                error_phase = "evaluation_input"
                break
            dest = staging / f"{art}{src.suffix or '.json'}"
            dest.write_bytes(src.read_bytes())
            artifacts_map[str(art)] = str(dest)

    evaluator_raw: dict[str, Any] | None = None
    eval_extension_meta: dict[str, Any] = {}
    if error_phase is None:
        # evaluation_input_contribute + evaluation_runtime (fail closed).
        contrib_ctx = {
            "artifacts": dict(artifacts_map),
            "eval_inputs": list(eval_inputs),
            "published": dict(published),
            "staging": str(staging),
            "package_root": str(package_root),
        }
        contrib = hook_evaluation_input(lock, contrib_ctx)
        if isinstance(contrib, dict):
            extra_arts = contrib.get("artifacts")
            if isinstance(extra_arts, dict):
                for k, v in extra_arts.items():
                    p = Path(str(v))
                    if p.is_file():
                        artifacts_map[str(k)] = str(p)
            eval_extension_meta["evaluation_input"] = {
                "keys": sorted(artifacts_map.keys()),
            }
        runtime_ann = hook_evaluation_runtime(lock, {"source": "package", "path": "run_command"})
        if runtime_ann is not None:
            eval_extension_meta["evaluation_runtime"] = (
                dict(runtime_ann) if isinstance(runtime_ann, dict) else {"value": runtime_ann}
            )
        evaluator_raw = run_evaluator_worker(
            package_root,
            lock,
            artifacts_map,
            database_root=resolved.database_root,
        )
        if isinstance(evaluator_raw, dict):
            evaluator_raw = hook_score_postprocess(lock, evaluator_raw)
            if not isinstance(evaluator_raw, dict):
                raise RuntimeError("score_postprocess_must_return_dict")
    timer.add_ms("evaluate", (_mono() - eval_t0) * 1000.0)

    # Cleanup agent materialization
    cleanup_t0 = _mono()
    hook_cleanup(lock)
    agent_file = package_root / ".bora_agent_result.json"
    if agent_file.exists():
        agent_file.unlink()
    workspace_handoff = package_root / ".bora_workspace_output.json"
    if workspace_handoff.exists():
        workspace_handoff.unlink()

    evidence_locator = portable_run_locator(run_dir, database_root=resolved.database_root)
    # Finalize §8.9 evidence tree when store was created (session path).
    if evidence_store is not None:
        with contextlib.suppress(Exception):
            evidence_store.write_harness_terminal(
                {
                    "kind": harness_kind,
                    "envelope_ok": bool(envelope.get("ok")),
                    "terminal": envelope.get("terminal"),
                }
            )
        if evaluator_raw is not None:
            with contextlib.suppress(Exception):
                evidence_store.write_evaluation("raw", dict(evaluator_raw))
        with contextlib.suppress(Exception):
            evidence_store.write_cleanup(
                {
                    "ok": True,
                    "warning": None,
                    "agent_invocations": agent_invocations,
                }
            )
        evidence_locator = evidence_store.locator
    timer.add_ms("cleanup", (_mono() - cleanup_t0) * 1000.0)

    flat = bind_result(
        evaluator_raw=evaluator_raw,
        harness_kind=harness_kind,
        # docker kind preflight does not upgrade isolation grade until full L1 workload.
        runtime_kind="local_l0",
        agent_invocations=agent_invocations,
        evidence_path=evidence_locator,
        error_phase=error_phase,
        logs=evidence_locator,
        assurance=assurance,
    )
    result_doc = flat.as_dict()
    result_doc["assurance"] = assurance
    if l1_meta:
        result_doc["l1"] = l1_meta
    if eval_extension_meta:
        result_doc["evaluation_extensions"] = eval_extension_meta
    phase_timing = timer.as_dict()
    result_doc["phase_timing"] = phase_timing
    result_doc["duration"] = format_duration_ms(phase_timing.get("total_ms"))
    (run_dir / "result.json").write_text(
        json.dumps(result_doc, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "harness.json").write_text(
        json.dumps(
            seal_harness_for_evidence(harness_out, run_dir=run_dir),
            sort_keys=True,
            default=str,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "agent.json").write_text(
        json.dumps(agent_meta, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if evidence_store is not None:
        with contextlib.suppress(Exception):
            evidence_store.write_summary(
                {
                    "status": flat.status,
                    "score": flat.score,
                    "agent_invocations": agent_invocations,
                    "harness_kind": harness_kind,
                    "logs": evidence_locator,
                    "result": result_doc,
                    "phase_timing": phase_timing,
                    "started_at": phase_timing.get("started_at"),
                    "finished_at": phase_timing.get("finished_at"),
                }
            )

    if flat.status == "PASS":
        code = 0
    elif flat.status == "FAIL":
        code = 1
    else:
        code = 2
    details = {
        "agent": agent_meta,
        "harness": harness_out,
        # Sealed / reported locator is portable; host abs kept out of result products.
        "run_dir": evidence_locator,
        "assurance": assurance,
        "digest": lock.digest,
        "logs": evidence_locator,
        "phase_timing": phase_timing,
        "metrics": flat.metrics,
    }
    if l1_meta:
        details["l1"] = l1_meta
    return code, flat, details
