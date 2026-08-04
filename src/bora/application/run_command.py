"""Production ``bora run`` use case — Core 1–5 vertical slice (v0.6)."""

from __future__ import annotations

import contextlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from bora.adapters.package_fs import LocalPackageReader
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
) -> tuple[int, FlatResult, dict[str, Any]]:
    """Run one foreground Attempt and return (exit_code, result, details)."""
    package_root = package_root.resolve()
    # Host credential locators from .env (values never enter lock/evidence).
    from bora.application.env_bootstrap import load_host_env_files

    load_host_env_files(package_root=package_root)
    config = ConfigCore(package_reader=LocalPackageReader())
    try:
        lock = config.load_and_lock(
            package_root,
            task_id,
            overrides=overrides,
            capabilities=DeclarationCapabilityCatalog(),
        )
    except ConfigError:
        # unknown task etc. before Attempt/evidence
        raise

    evidence_root = (evidence_root or (package_root / ".bora" / "runs")).resolve()
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

    # Parent Agent Service: if package declares a codex profile, try one real invoke.
    profiles = thaw(lock.agent_profiles)
    params = thaw(lock.parameters)
    evaluation = thaw(lock.evaluation)
    provider_cfg = thaw(lock.provider)
    provider_kind = str(provider_cfg.get("kind") or "local")
    agent_profile = next((p for p in profiles if isinstance(p, dict)), None)
    use_agent_session = bool(params.get("use_agent_session"))
    agent_service = None
    agent_server = None
    agent_sock_path = None
    shared_attempt = None  # Runtime-owned Attempt shared with harness worker
    if use_agent_session and agent_profile is not None:
        from bora.adapters.agent_openai_http import resolve_executor
        from bora.runtime.agent_service import AgentServiceServer, ParentAgentService

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
            evidence_store.write_lock_summary(
                {
                    "digest": lock.digest,
                    "task_id": task_id,
                    "profiles": profile_rows,
                }
            )
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
            resolve_executor=lambda kind, model, **kw: resolve_executor(
                kind, model=model, **kw
            ),
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
    elif agent_profile is not None and provider_kind != "docker":
        # Docker/L1 packages own agent+workspace orchestration in the docker branch.
        from bora.adapters.agent_openai_http import resolve_executor

        model = str(agent_profile.get("model") or "gpt-5.4-mini")
        kind = str(agent_profile.get("executor") or "codex")
        question = str(params.get("question") or 'Return JSON {"answer": 42}')
        try:
            executor = resolve_executor(
                kind,
                model=model,
                base_url=(
                    str(agent_profile.get("base_url"))
                    if agent_profile.get("base_url")
                    else None
                ),
                api_key=(
                    str(agent_profile.get("api_key"))
                    if agent_profile.get("api_key")
                    else None
                ),
            )
        except KeyError:
            flat = bind_result(
                evaluator_raw=None,
                harness_kind="failed",
                runtime_kind="local_l0",
                agent_invocations=0,
                evidence_path=str(run_dir),
                error_phase="config",
            )
            return 2, flat, {"error": {"kind": "executor_unknown", "executor": kind}}
        workspace_root: Path | None = None
        # Generic file-workspace mode: declared relative output under Attempt workdir.
        if params.get("workspace_output") and not use_agent_session:
            # Type B: seed Attempt workdir, run Agent with cwd=workdir, collect file artifact.
            workspace_root = run_dir / "agent_workspace"
            if workspace_root.exists():
                shutil.rmtree(workspace_root)
            workspace_root.mkdir(parents=True)
            seed_dir = package_root / "data"
            if seed_dir.is_dir():
                for src in seed_dir.iterdir():
                    if src.is_file():
                        shutil.copy2(src, workspace_root / src.name)
            instruction_path = package_root / "data" / "instruction.md"
            if not instruction_path.is_file():
                instruction_path = package_root / "instruction.md"
            if instruction_path.is_file():
                question = instruction_path.read_text(encoding="utf-8")
            out_name = str(params.get("workspace_output") or "aggregates.json")
            out_path = Path(out_name)
            if out_path.is_absolute() or ".." in out_path.parts:
                flat = bind_result(
                    evaluator_raw=None,
                    harness_kind="failed",
                    runtime_kind="local_l0",
                    agent_invocations=0,
                    evidence_path=str(run_dir),
                    error_phase="config",
                )
                summary = flat.as_dict()
                summary["status"] = "ERROR"
                summary["error"] = {
                    "phase": "config",
                    "kind": "workspace_output_invalid",
                    "message": "workspace_output must be a relative non-escaping path",
                }
                (run_dir / "result.json").write_text(
                    json.dumps(summary, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                return 2, flat, {"error": summary["error"]}
            # Longer timeout for file-writing agents.
            invoke_timeout = float(params.get("agent_timeout_seconds") or 180)
            result = executor.invoke(question, timeout=invoke_timeout, workdir=str(workspace_root))
            agent_invocations = 1
            agent_meta = {
                "model": result.model,
                "ok": result.ok,
                "error": result.error,
                "executor": kind,
                "workdir": str(workspace_root),
            }
            out_file = workspace_root / out_name
            # Terminal class succeeds when the declared file exists (even if stdout is non-JSON).
            if not out_file.is_file():
                if not result.ok and not allow_offline_agent:
                    flat = bind_result(
                        evaluator_raw=None,
                        harness_kind="failed",
                        runtime_kind="local_l0",
                        agent_invocations=agent_invocations,
                        evidence_path=str(run_dir),
                        error_phase="agent",
                    )
                    summary = flat.as_dict()
                    summary["assurance"] = "l0"
                    summary["status"] = "ERROR"
                    summary["error"] = {
                        "phase": "agent",
                        "kind": result.error or "workspace_output_missing",
                        "message": f"terminal workspace missing {out_name}: {result.error}",
                    }
                    (run_dir / "result.json").write_text(
                        json.dumps(summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    (run_dir / "agent.json").write_text(
                        json.dumps(agent_meta, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    return 2, flat, {"agent": agent_meta, "assurance": "l0"}
                if not allow_offline_agent:
                    flat = bind_result(
                        evaluator_raw=None,
                        harness_kind="failed",
                        runtime_kind="local_l0",
                        agent_invocations=agent_invocations,
                        evidence_path=str(run_dir),
                        error_phase="agent",
                    )
                    summary = flat.as_dict()
                    summary["assurance"] = "l0"
                    summary["status"] = "ERROR"
                    summary["error"] = {
                        "phase": "agent",
                        "kind": "workspace_output_missing",
                        "message": f"declared workspace output missing: {out_name}",
                    }
                    (run_dir / "result.json").write_text(
                        json.dumps(summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    return 2, flat, {"agent": agent_meta, "assurance": "l0"}
            else:
                # Stage for harness: copy into package-relative handoff.
                handoff = package_root / ".bora_workspace_output.json"
                handoff.write_bytes(out_file.read_bytes())
                agent_meta["workspace_output"] = out_name
                agent_meta["workspace_output_bytes"] = out_file.stat().st_size
        else:
            result = executor.invoke(question)
            agent_invocations = 1
            agent_meta = {
                "model": result.model,
                "ok": result.ok,
                "error": result.error,
                "executor": kind,
            }
            if not result.ok:
                # Fail closed: do not start harness/evaluator with missing/stale agent material.
                # Tests may set allow_offline_agent only for explicit doubles, never production CLI.
                if not allow_offline_agent:
                    flat = bind_result(
                        evaluator_raw=None,
                        harness_kind="failed",
                        runtime_kind="local_l0",
                        agent_invocations=agent_invocations,
                        evidence_path=str(run_dir),
                        error_phase="agent",
                    )
                    summary = flat.as_dict()
                    summary["assurance"] = "l0"
                    summary["status"] = "ERROR"
                    summary["error"] = {
                        "phase": "agent",
                        "kind": result.error or "agent_failed",
                        "message": f"executor {kind} failed: {result.error}",
                    }
                    (run_dir / "result.json").write_text(
                        json.dumps(summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    (run_dir / "agent.json").write_text(
                        json.dumps(agent_meta, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    return 2, flat, {"agent": agent_meta, "assurance": "l0"}
                agent_meta["offline_fallback"] = True
            else:
                # Only structured agent output is materializable; never invent answer:42.
                if not isinstance(result.structured, dict):
                    flat = bind_result(
                        evaluator_raw=None,
                        harness_kind="failed",
                        runtime_kind="local_l0",
                        agent_invocations=agent_invocations,
                        evidence_path=str(run_dir),
                        error_phase="agent",
                    )
                    summary = flat.as_dict()
                    summary["assurance"] = "l0"
                    summary["status"] = "ERROR"
                    summary["error"] = {
                        "phase": "agent",
                        "kind": "agent_output_unstructured",
                        "message": "executor returned no parseable structured object",
                    }
                    (run_dir / "result.json").write_text(
                        json.dumps(summary, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    return 2, flat, {"agent": agent_meta, "assurance": "l0"}
                payload = result.structured
                agent_file.write_text(
                    json.dumps(payload, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

    if provider_kind == "docker":
        # Full L1 orchestration for all docker packages (Spec 07) — no preflight-only PASS.
        from bora.application.run_l1 import run_l1_attempt
        from bora.evaluation.result_binding import FlatResult

        code, result_doc, details = run_l1_attempt(
            package_root=package_root,
            lock=lock,
            run_dir=run_dir,
            agent_meta=agent_meta,
            agent_invocations=agent_invocations,
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
        from bora.environment.manager import EnvironmentManager
        from bora.evidence.store import AttemptEvidenceStore

        env_meta: dict[str, Any] = {"resource": "postgresql", "manager": True}
        try:
            limits_map = thaw(lock.limits) if hasattr(lock, "limits") else {}
            action_limit = int(
                (limits_map or {}).get("environment_actions") or 10  # type: ignore[union-attr]
            )
            # Ensure §8.9 evidence root exists for effects.jsonl even without Agent Session.
            if evidence_store is None:
                evidence_store = AttemptEvidenceStore(
                    root=run_dir,
                    attempt_id=str(agent_meta.get("attempt_id") or run_id),
                    run_id=run_id,
                )
            env_manager = EnvironmentManager(
                attempt_id=str(agent_meta.get("attempt_id") or run_id),
                action_limit=max(1, action_limit),
                evidence_store=evidence_store,
            )
            opened = env_manager.open_resource("postgresql", name=f"bora-env-{run_id[:10]}")
            if not opened.get("ok"):
                raise RuntimeError(opened.get("error") or "open_resource_failed")
            rid = str(opened["resource_id"])
            # Resource-type handoff only: container locator for package Tools.
            # No Benchmark/task/domain branch; package may ship environment/seed.sql.
            container = rid.split(":", 1)[-1] if ":" in rid else rid
            seed_file = package_root / "environment" / "seed.sql"
            seed_applied = False
            if seed_file.is_file():
                for stmt in _split_sql_statements(seed_file.read_text(encoding="utf-8")):
                    r = env_manager.action(rid, "execute", {"sql": stmt})
                    if not r.get("ok"):
                        raise RuntimeError(f"environment seed failed: {r}")
                seed_applied = True
            # Generic readiness probe (resource protocol only — no package table names).
            health = env_manager.action(rid, "query", {"sql": "SELECT 1"})
            if not health.get("ok"):
                raise RuntimeError(f"environment health failed: {health}")
            snap = env_manager.freeze_snapshot(rid)
            # Optional Spec 15 public negative: undeclared/dangerous action before mutation.
            deny_probe: dict[str, Any] | None = None
            if str(params.get("probe_mode") or "") == "undeclared_action":
                # Unknown action id — Manager/Adapter must refuse before external effect.
                denied = env_manager.action(rid, "drop_schema", {"sql": "DROP TABLE x"})
                # Dangerous SQL on allowed execute surface — adapter fail closed.
                denied_sql = env_manager.action(
                    rid, "execute", {"sql": "DROP TABLE IF EXISTS probe_denied_table"}
                )
                deny_probe = {
                    "unknown_action": denied,
                    "dangerous_sql": denied_sql,
                    "denied_before_mutation": (
                        denied.get("ok") is False and denied_sql.get("ok") is False
                    ),
                    "mutation_executed": False,
                }
            # Connection recipe for Harness Tools — never gold / business answers.
            env_doc = {
                "ok": True,
                "resource": "postgresql",
                "resource_id": rid,
                "container": container,
                "user": "bora",
                "password": "bora-attempt",
                "database": "bora",
                "seed_applied": seed_applied,
                "snapshot": snap,
                "action_count": env_manager._actions,
                "deny_probe": deny_probe,
            }
            (package_root / ".bora_env_result.json").write_text(
                json.dumps(env_doc, sort_keys=True) + "\n", encoding="utf-8"
            )
            env_meta.update(
                {
                    "ok": True,
                    "ready": True,
                    "resource_id": rid,
                    "container": container,
                    "seed_applied": seed_applied,
                }
            )
        except Exception as exc:  # noqa: BLE001
            env_doc = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            (package_root / ".bora_env_result.json").write_text(
                json.dumps(env_doc, sort_keys=True) + "\n", encoding="utf-8"
            )
            env_meta.update({"ok": False, "error": str(exc)})
            flat = bind_result(
                evaluator_raw=None,
                harness_kind="failed",
                runtime_kind="local_l0",
                agent_invocations=0,
                evidence_path=str(run_dir),
                error_phase="environment",
            )
            summary = flat.as_dict()
            summary["assurance"] = "l0"
            summary["status"] = "ERROR"
            summary["error"] = {
                "phase": "environment",
                "kind": "environment_prepare_failed",
                "message": str(exc),
            }
            (run_dir / "result.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            if env_manager is not None:
                with contextlib.suppress(Exception):
                    env_manager.close()
            return 2, flat, {"environment": env_meta, "assurance": "l0"}
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
        evaluator_raw = _run_evaluator_worker(package_root, lock, artifacts_map)

    # Cleanup agent materialization
    agent_file = package_root / ".bora_agent_result.json"
    if agent_file.exists():
        agent_file.unlink()
    workspace_handoff = package_root / ".bora_workspace_output.json"
    if workspace_handoff.exists():
        workspace_handoff.unlink()

    evidence_locator = str(run_dir)
    relative_evidence = str(
        run_dir.relative_to(package_root) if run_dir.is_relative_to(package_root) else run_dir
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


def _split_sql_statements(sql_text: str) -> list[str]:
    """Split package seed.sql into single statements (strip comments/empties)."""
    stmts: list[str] = []
    buf: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                stmts.append(stmt)
            buf = []
    tail = "\n".join(buf).strip().rstrip(";").strip()
    if tail:
        stmts.append(tail)
    return stmts


def _run_evaluator_worker(
    package_root: Path,
    lock: Any,
    artifacts_map: dict[str, str],
) -> dict[str, Any]:
    """Run package evaluator in a dedicated subprocess (not parent import)."""
    import os
    import subprocess
    import tempfile

    path = package_root / "evaluator.py"
    if not path.is_file():
        return {"status": "ERROR", "score": None, "metrics": {}}
    with tempfile.TemporaryDirectory(prefix="bora-eval-") as tmp:
        script = Path(tmp) / "run_eval.py"
        out_path = Path(tmp) / "out.json"
        script.write_text(
            "\n".join(
                [
                    "import json, importlib.util",
                    f"spec = importlib.util.spec_from_file_location('ev', {str(path)!r})",
                    "mod = importlib.util.module_from_spec(spec)",
                    "assert spec.loader is not None",
                    "spec.loader.exec_module(mod)",
                    f"raw = mod.evaluate({{'artifacts': {json.dumps(artifacts_map)}}})",
                    f"open({str(out_path)!r}, 'w', encoding='utf-8').write(json.dumps(raw))",
                ]
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(script)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        if proc.returncode != 0 or not out_path.is_file():
            return {
                "status": "ERROR",
                "score": None,
                "metrics": {"stderr": (proc.stderr or "")[-500:]},
            }
        raw = json.loads(out_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"status": "ERROR", "score": None, "metrics": {}}
        return raw
