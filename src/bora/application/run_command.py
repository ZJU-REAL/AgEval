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
from bora.application.run_command_environment import prepare_postgresql_environment
from bora.application.run_command_evaluator import run_evaluator_worker
from bora.application.run_harness import run_harness_package
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw
from bora.evaluation.result_binding import FlatResult, bind_result


async def run_task(
    package_root: Path,
    task_id: str,
    *,
    evidence_root: Path | None = None,
    allow_offline_agent: bool = False,
    overrides: dict[str, Any] | None = None,
    profiles_path: Path | str | None = None,
    profile_bindings: dict[str, dict[str, Any]] | None = None,
) -> tuple[int, FlatResult, dict[str, Any]]:
    """Run one foreground Attempt and return (exit_code, result, details).

    *package_root* is the **Database** root (``bora.database/1``). Member
    ``task.yaml`` is resolved via ``resolve_task``; the task directory is the
    package root for harness/evaluator relative paths.
    """
    from bora.application.env_bootstrap import load_host_env_files
    from bora.config.database import resolve_task
    from bora.config.profiles import resolve_profile_bindings
    from bora.registry.resolve import resolve_database_root

    database_root = resolve_database_root(package_root)
    resolved = resolve_task(database_root, task_id)
    package_root = resolved.task_dir
    from bora.config.database import load_database_manifest

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

    # Never trust residual agent materialization from a previous run/package tree.
    agent_file = package_root / ".bora_agent_result.json"
    if agent_file.exists():
        agent_file.unlink()

    # Parent Agent Service: non-empty agent_profiles ⇒ harness session/invoke (L0 only).
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
        from bora.adapters.agent_registry import resolve_executor
        from bora.runtime.agent_service_protocol import AgentServiceServer
        from bora.runtime.parent_agent_service import ParentAgentService

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
            evidence_store.write_lock_summary(lock_doc)
        # Wall hard ceiling from locked limits (design §13.1): pre-effect deadline.
        import time as _time

        try:
            wall_s = float(thaw(lock.limits).get("wall_time_seconds") or 0)  # type: ignore[union-attr]
        except Exception:
            wall_s = 0.0
        deadline = (_time.monotonic() + wall_s) if wall_s > 0 else None
        agent_service = ParentAgentService(
            profiles=[p for p in profiles if isinstance(p, dict)],
            agent_invocation_limit=inv_limit,
            resolve_executor=lambda kind, model, **kw: resolve_executor(kind, model=model, **kw),
            attempt_id=attempt_ident.value,
            evidence_store=evidence_store,
            deadline_monotonic=deadline,
        )
        agent_meta["wall_time_seconds"] = wall_s if wall_s > 0 else None
        agent_meta["deadline_armed"] = deadline is not None
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
        # Full L1 orchestration for all docker packages (Spec 07) — no preflight-only PASS.
        from bora.application.run_l1 import run_l1_attempt

        code, result_doc, details = run_l1_attempt(
            package_root=package_root,
            lock=lock,
            run_dir=run_dir,
            agent_meta=agent_meta,
            allow_offline_agent=allow_offline_agent,
        )
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
            evidence_path=str(result_doc.get("evidence_path") or run_dir),
            runtime_kind=str(result_doc.get("runtime_kind") or "docker_l1"),
            harness_kind=str(result_doc.get("harness_kind") or "failed"),
            agent_invocations=int(result_doc.get("agent_invocations") or 0),
            assurance=str(result_doc.get("assurance") or "l0"),
            logs=str(result_doc.get("logs") or run_dir),
        )
        details = {**details, "logs": flat.logs}
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
            return early
        agent_meta["environment"] = env_meta
        (run_dir / "env_manager.json").write_text(
            json.dumps({"resource_id": env_meta.get("resource_id")}, sort_keys=True) + "\n",
            encoding="utf-8",
        )

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
        harness_out = await run_harness_package(
            lock,
            package_root,
            timeout_seconds=harness_timeout,
            agent_service_sock=str(agent_sock_path) if agent_sock_path else None,
            # Reuse ParentAgentService identity so AgentSession + harness share one Attempt.
            attempt=shared_attempt,
        )
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
        # Environment Manager teardown
        if env_manager is not None:
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
    if error_phase is None:
        evaluator_raw = run_evaluator_worker(package_root, lock, artifacts_map)

    # Cleanup agent materialization
    agent_file = package_root / ".bora_agent_result.json"
    if agent_file.exists():
        agent_file.unlink()
    workspace_handoff = package_root / ".bora_workspace_output.json"
    if workspace_handoff.exists():
        workspace_handoff.unlink()

    evidence_locator = str(run_dir)
    relative_evidence = str(
        run_dir.relative_to(resolved.database_root)
        if run_dir.is_relative_to(resolved.database_root)
        else run_dir
    )
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

    flat = bind_result(
        evaluator_raw=evaluator_raw,
        harness_kind=harness_kind,
        # docker kind preflight does not upgrade isolation grade until full L1 workload.
        runtime_kind="local_l0",
        agent_invocations=agent_invocations,
        evidence_path=relative_evidence,
        error_phase=error_phase,
        logs=evidence_locator,
        assurance=assurance,
    )
    result_doc = flat.as_dict()
    result_doc["assurance"] = assurance
    if l1_meta:
        result_doc["l1"] = l1_meta
    (run_dir / "result.json").write_text(
        json.dumps(result_doc, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "harness.json").write_text(
        json.dumps(harness_out, sort_keys=True, default=str, indent=2) + "\n",
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
        "run_dir": str(run_dir),
        "assurance": assurance,
        "digest": lock.digest,
        "logs": evidence_locator,
    }
    if l1_meta:
        details["l1"] = l1_meta
    return code, flat, details
