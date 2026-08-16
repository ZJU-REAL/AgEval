"""L0 Attempt phase helpers — called by LocalL0Stages."""

from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path
from typing import Any

from bora.application.attempt.attempt_stages import AttemptStageContext
from bora.application.attempt.phase_timing import PhaseTimer, format_duration_ms
from bora.application.attempt.run_command_environment import prepare_postgresql_environment
from bora.application.attempt.run_command_evaluator import run_evaluator_worker
from bora.application.attempt.run_harness import run_harness_package
from bora.config.model import thaw
from bora.evaluation.result_binding import FlatResult, bind_result
from bora.evidence.locators import portable_run_locator, seal_harness_for_evidence
from bora.evidence.store import AttemptEvidenceStore
from bora.runtime.identity import AttemptIdentity


def _timer(ctx: AttemptStageContext) -> PhaseTimer:
    if ctx.timer is None:
        ctx.timer = PhaseTimer()
    return ctx.timer


def _attempt(ctx: AttemptStageContext) -> AttemptIdentity:
    if ctx.attempt is None:
        raise TypeError("LocalL0Stages requires a caller-owned Attempt identity")
    return ctx.attempt


def prepare_postgresql_on_ctx(
    ctx: AttemptStageContext,
) -> tuple[int, FlatResult, dict[str, Any]] | None:
    """Open postgresql when the lock asks for it. Returns an early result on failure."""
    params = thaw(ctx.lock.parameters)
    if (
        not isinstance(params, dict)
        or str(params.get("environment_resource") or "") != "postgresql"
    ):
        return None
    attempt = _attempt(ctx)
    env_manager, evidence_store, env_meta, early = prepare_postgresql_environment(
        package_root=ctx.package_root,
        lock=ctx.lock,
        run_dir=ctx.run_dir,
        run_id=attempt.trial.run.value,
        params=params,
        agent_meta=ctx.agent_meta,
        evidence_store=ctx.evidence_store,
    )
    if early is not None:
        return early
    ctx.env_manager = env_manager
    ctx.evidence_store = evidence_store
    ctx.agent_meta["environment"] = env_meta
    (ctx.run_dir / "env_manager.json").write_text(
        json.dumps({"resource_id": env_meta.get("resource_id")}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return None


def write_l0_lock_summary(ctx: AttemptStageContext) -> None:
    if ctx.evidence_store is None:
        return
    with contextlib.suppress(Exception):
        from bora.adapters.executor_capabilities import get_capabilities

        profiles = thaw(ctx.lock.agent_profiles)
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
            from bora.config.profiles import acp_entry_from_binding

            entry = acp_entry_from_binding(p)
            if entry is not None:
                row["options"] = {"entry": entry}
            if p.get("base_url"):
                row["base_url"] = p.get("base_url")
            if p.get("api_key"):
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
            "digest": ctx.lock.digest,
            "task_id": ctx.task_id,
            "profiles": profile_rows,
        }
        if ctx.lock.provenance is not None:
            lock_doc["provenance"] = thaw(ctx.lock.provenance)
        if ctx.lock.job_overlay is not None:
            lock_doc["job_overlay"] = thaw(ctx.lock.job_overlay)
        ctx.evidence_store.write_lock_summary(lock_doc)


def prepare_l0_attempt(ctx: AttemptStageContext) -> tuple[int, FlatResult, dict[str, Any]] | None:
    """Evidence, env, agent service + socket. Returns early result on env failure."""
    import tempfile
    import time

    from bora.application.attempt.agent_service_assemble import (
        assemble_parent_agent_service,
        read_wall_deadline,
    )
    from bora.application.attempt.extension_hooks import hook_prepare
    from bora.runtime.agent_service_protocol import AgentServiceServer

    timer = _timer(ctx)
    attempt = _attempt(ctx)
    with timer.phase("prepare"):
        early = prepare_postgresql_on_ctx(ctx)
        if early is not None:
            code, flat, details = early
            ctx.exit_code = code
            ctx.result_doc = flat.as_dict()
            ctx.details = details
            return early

        profiles = thaw(ctx.lock.agent_profiles)
        params = thaw(ctx.lock.parameters)
        agent_profile = next((p for p in profiles if isinstance(p, dict)), None)
        if agent_profile is not None:
            try:
                inv_limit = int(thaw(ctx.lock.limits).get("agent_invocations") or 1)
            except Exception:
                inv_limit = 1
            if ctx.evidence_store is None:
                ctx.evidence_store = AttemptEvidenceStore(
                    root=ctx.run_dir,
                    attempt_id=attempt.value,
                    run_id=attempt.trial.run.value,
                    database_root=ctx.database_root,
                )
            write_l0_lock_summary(ctx)
            from types import SimpleNamespace

            from bora.application.attempt.extension_hooks import hook_home_overlay

            workspace_root = ctx.run_dir / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            overlay_ctx = SimpleNamespace(
                work_root=ctx.run_dir,
                package_root=ctx.database_root or ctx.package_root,
                workspace_root=workspace_root,
            )
            overlay_value = hook_home_overlay(
                ctx.lock,
                {
                    "package_root": str(ctx.database_root or ctx.package_root),
                    "workspace_root": str(workspace_root),
                    "work_root": str(ctx.run_dir),
                },
                ctx=overlay_ctx,
            )
            attempt_home = None
            if isinstance(overlay_value, dict):
                attempt_home = overlay_value.get("home_root")
            wall_s, deadline = read_wall_deadline(lock=ctx.lock, monotonic_now=time.monotonic())
            ctx.wall_s = wall_s
            service, invoke_timeout, authority = assemble_parent_agent_service(
                profiles=profiles if isinstance(profiles, list) else [],
                package_root=ctx.package_root,
                attempt=attempt,
                inv_limit=inv_limit,
                params=params if isinstance(params, dict) else {},
                evidence_store=ctx.evidence_store,
                deadline_monotonic=deadline,
                home=attempt_home,
            )
            ctx.agent_service = service
            ctx.authority = authority
            ctx.agent_meta["wall_time_seconds"] = wall_s if wall_s > 0 else None
            ctx.agent_meta["deadline_armed"] = deadline is not None
            ctx.agent_meta["invoke_timeout_seconds"] = invoke_timeout
            sock = Path(tempfile.gettempdir()) / f"bora-ags-{attempt.trial.run.value[:12]}.sock"
            ctx.agent_sock_path = sock
            ctx.agent_server = AgentServiceServer(service, sock)
            ctx.agent_server.start()
        hook_prepare(ctx.lock)
    return None


async def run_l0_harness(ctx: AttemptStageContext) -> None:
    from bora.application.attempt.extension_hooks import hook_run

    timer = _timer(ctx)
    attempt = _attempt(ctx)
    params = thaw(ctx.lock.parameters)
    with timer.phase("run"):
        harness_timeout = (
            float(params.get("harness_timeout_seconds") or 300.0)
            if isinstance(params, dict)
            else 300.0
        )
        try:
            wall_cap = float(thaw(ctx.lock.limits).get("wall_time_seconds") or 0)
        except Exception:
            wall_cap = 0.0
        if wall_cap > 0:
            harness_timeout = min(harness_timeout, wall_cap)
        hook_run(ctx.lock)
        ctx.harness_out = await run_harness_package(
            ctx.lock,
            ctx.package_root,
            timeout_seconds=harness_timeout,
            agent_service_sock=str(ctx.agent_sock_path) if ctx.agent_sock_path else None,
            attempt=attempt,
            database_root=ctx.database_root,
        )
    if ctx.agent_service is not None:
        ctx.inv_count = ctx.agent_service.invocations_completed
        ctx.agent_meta = {
            **ctx.agent_meta,
            "mode": "parent_agent_service",
            "invocations": ctx.inv_count,
        }


def seal_l0_inputs(ctx: AttemptStageContext) -> None:
    if ctx.agent_server is not None:
        ctx.agent_server.stop()
        ctx.agent_server = None
    envelope = ctx.harness_out.get("envelope") or {}
    ctx.envelope = envelope if isinstance(envelope, dict) else {}
    harness_kind = "failed"
    if ctx.envelope.get("ok") and ctx.envelope.get("terminal", {}).get("kind") == "completed":
        harness_kind = "completed"
    elif ctx.envelope.get("ok"):
        harness_kind = str(ctx.envelope.get("terminal", {}).get("kind", "unknown"))
    ctx.harness_kind = harness_kind

    evaluation = thaw(ctx.lock.evaluation)
    published = dict(ctx.envelope.get("published") or {})
    eval_inputs = list(evaluation.get("inputs") or [])
    staging = ctx.run_dir / "eval_staging"
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
    ctx.artifacts_map = artifacts_map
    ctx.error_phase = error_phase


def evaluate_l0(ctx: AttemptStageContext) -> None:
    from bora.application.attempt.extension_hooks import (
        hook_evaluate,
        hook_evaluation_input,
        hook_evaluation_runtime,
        hook_score_postprocess,
    )

    timer = _timer(ctx)
    attempt = _attempt(ctx)
    with timer.phase("evaluate"):
        hook_evaluate(ctx.lock)
        if ctx.error_phase is not None:
            return
        evaluation = thaw(ctx.lock.evaluation)
        contrib_ctx = {
            "artifacts": dict(ctx.artifacts_map),
            "eval_inputs": list(evaluation.get("inputs") or []),
            "published": dict(ctx.envelope.get("published") or {}),
            "staging": str(ctx.run_dir / "eval_staging"),
            "package_root": str(ctx.package_root),
        }
        contrib = hook_evaluation_input(ctx.lock, contrib_ctx)
        if isinstance(contrib, dict):
            extra_arts = contrib.get("artifacts")
            if isinstance(extra_arts, dict):
                for k, v in extra_arts.items():
                    p = Path(str(v))
                    if p.is_file():
                        ctx.artifacts_map[str(k)] = str(p)
            ctx.eval_extension_meta["evaluation_input"] = {
                "keys": sorted(ctx.artifacts_map.keys()),
            }
        runtime_ann = hook_evaluation_runtime(
            ctx.lock, {"source": "package", "path": "run_command"}
        )
        if runtime_ann is not None:
            ctx.eval_extension_meta["evaluation_runtime"] = (
                dict(runtime_ann) if isinstance(runtime_ann, dict) else {"value": runtime_ann}
            )
        evaluator_raw = run_evaluator_worker(
            ctx.package_root,
            ctx.lock,
            ctx.artifacts_map,
            database_root=ctx.database_root,
            attempt=attempt,
        )
        if isinstance(evaluator_raw, dict):
            evaluator_raw = hook_score_postprocess(ctx.lock, evaluator_raw)
            if not isinstance(evaluator_raw, dict):
                raise RuntimeError("score_postprocess_must_return_dict")
        ctx.evaluator_raw = evaluator_raw


def bind_l0_result(ctx: AttemptStageContext) -> None:
    timer = _timer(ctx)
    locator = portable_run_locator(ctx.run_dir, database_root=ctx.database_root)
    if ctx.evidence_store is not None:
        with contextlib.suppress(Exception):
            ctx.evidence_store.write_harness_terminal(
                {
                    "kind": ctx.harness_kind,
                    "envelope_ok": bool(ctx.envelope.get("ok")),
                    "terminal": ctx.envelope.get("terminal"),
                }
            )
        if ctx.evaluator_raw is not None:
            with contextlib.suppress(Exception):
                ctx.evidence_store.write_evaluation("raw", dict(ctx.evaluator_raw))
        locator = ctx.evidence_store.locator
    flat = bind_result(
        evaluator_raw=ctx.evaluator_raw,
        harness_kind=ctx.harness_kind,
        runtime_kind="local_l0",
        agent_invocations=ctx.inv_count,
        evidence_path=locator,
        error_phase=ctx.error_phase,
        logs=locator,
        assurance="l0",
    )
    result_doc = flat.as_dict()
    result_doc["assurance"] = "l0"
    if ctx.eval_extension_meta:
        result_doc["evaluation_extensions"] = ctx.eval_extension_meta
    phase_timing = timer.as_dict()
    result_doc["phase_timing"] = phase_timing
    result_doc["duration"] = format_duration_ms(phase_timing.get("total_ms"))
    from bora.config.profiles import attach_display_labels

    attach_display_labels(
        result_doc,
        thaw(ctx.lock.job_overlay) if ctx.lock.job_overlay is not None else None,
    )
    from bora.evidence.attempt_record import write_attempt_result

    write_attempt_result(ctx.run_dir, result_doc)
    (ctx.run_dir / "harness.json").write_text(
        json.dumps(
            seal_harness_for_evidence(ctx.harness_out, run_dir=ctx.run_dir),
            sort_keys=True,
            default=str,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (ctx.run_dir / "agent.json").write_text(
        json.dumps(ctx.agent_meta, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if ctx.evidence_store is not None:
        with contextlib.suppress(Exception):
            ctx.evidence_store.write_summary(
                {
                    "status": flat.status,
                    "score": flat.score,
                    "agent_invocations": ctx.inv_count,
                    "harness_kind": ctx.harness_kind,
                    "logs": locator,
                    "result": result_doc,
                    "phase_timing": phase_timing,
                    "started_at": phase_timing.get("started_at"),
                    "finished_at": phase_timing.get("finished_at"),
                    "agent_label": result_doc.get("agent_label") or "",
                    "model_label": result_doc.get("model_label") or "",
                }
            )
    if flat.status == "PASS":
        code = 0
    elif flat.status == "FAIL":
        code = 1
    else:
        code = 2
    ctx.exit_code = code
    ctx.result_doc = result_doc
    ctx.details = {
        "agent": ctx.agent_meta,
        "harness": ctx.harness_out,
        "run_dir": locator,
        "assurance": "l0",
        "digest": ctx.lock.digest,
        "logs": locator,
        "phase_timing": phase_timing,
        "metrics": flat.metrics,
    }


def cleanup_l0(ctx: AttemptStageContext) -> None:
    from bora.application.attempt.extension_hooks import hook_cleanup

    timer = _timer(ctx)
    with timer.phase("cleanup"):
        if ctx.agent_server is not None:
            with contextlib.suppress(Exception):
                ctx.agent_server.stop()
            ctx.agent_server = None
        from bora.application.attempt.run_command_environment import (
            teardown_attempt_environment,
        )

        teardown_attempt_environment(ctx)
        hook_cleanup(ctx.lock)
        for leftover in (
            ctx.package_root / ".bora_agent_result.json",
            ctx.package_root / ".bora_workspace_output.json",
        ):
            if leftover.exists():
                with contextlib.suppress(OSError):
                    leftover.unlink()
        if ctx.evidence_store is not None:
            with contextlib.suppress(Exception):
                ctx.evidence_store.write_cleanup(
                    {
                        "ok": True,
                        "warning": None,
                        "agent_invocations": ctx.inv_count,
                    }
                )
