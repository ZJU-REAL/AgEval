"""L1 Attempt phase helpers — called by DockerL1Stages."""

from __future__ import annotations

import contextlib
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from bora.adapters.credential_projection import project_executor_credentials
from bora.application.attempt_stages import AttemptStageContext
from bora.application.phase_timing import PhaseTimer, format_duration_ms
from bora.application.run_l1 import (
    _database_root_for_run,
    _l1_host_cleanup,
)
from bora.application.run_l1_evaluator import run_clean_evaluator_container
from bora.application.run_l1_evidence import l1_error_result, write_l1_evidence
from bora.application.run_l1_prepare import (
    make_l1_placement_resolver,
    prepare_l1_runtime,
    seed_l1_workspace,
)
from bora.config.model import thaw
from bora.evaluation.result_binding import bind_result
from bora.evidence.locators import portable_run_locator
from bora.evidence.store import AttemptEvidenceStore
from bora.provider.isolation import parse_logical_topology
from bora.runtime.identity import AttemptIdentity, assert_same_attempt


def _timer(ctx: AttemptStageContext) -> PhaseTimer:
    if ctx.timer is None:
        ctx.timer = PhaseTimer()
    return ctx.timer


def _attempt(ctx: AttemptStageContext) -> AttemptIdentity:
    if ctx.attempt is None:
        raise TypeError("DockerL1Stages requires a caller-owned Attempt identity")
    return ctx.attempt


def _store_error(
    ctx: AttemptStageContext,
    phase: str,
    l1_meta: dict[str, Any],
    *,
    kind: str | None = None,
    inv: int = 0,
) -> None:
    timer = _timer(ctx)
    code, doc, details = l1_error_result(
        ctx.run_dir,
        phase,
        l1_meta,
        ctx.agent_meta,
        inv,
        kind=kind,
        phase_timing=timer.as_dict(),
    )
    ctx.exit_code = code
    ctx.result_doc = doc
    ctx.details = details


def prepare_l1_session(ctx: AttemptStageContext) -> bool:
    """Prepare runtime, creds, targets, and agent service. False = fail the stage."""
    from bora.application.agent_service_assemble import (
        assemble_parent_agent_service,
        read_wall_deadline,
    )
    from bora.application.run_l0 import prepare_postgresql_on_ctx
    from bora.runtime.agent_service_protocol import AgentServiceServer

    timer = _timer(ctx)
    attempt = _attempt(ctx)
    early = prepare_postgresql_on_ctx(ctx)
    if early is not None:
        return False

    params = thaw(ctx.lock.parameters)
    profiles = [p for p in thaw(ctx.lock.agent_profiles) if isinstance(p, dict)]
    if not profiles:
        _store_error(
            ctx,
            "config",
            {"error": "l1_dispatch_unsupported", "task_id": ctx.task_id or str(ctx.lock.task_id)},
            kind="l1_dispatch_unsupported",
        )
        return False

    provider_cfg = thaw(ctx.lock.provider) if hasattr(ctx.lock, "provider") else {}
    if not isinstance(provider_cfg, dict):
        provider_cfg = {}
    network_mode = str(provider_cfg.get("network") or "bridge")
    profile_ids = {str(p.get("id")) for p in profiles if p.get("id")}
    try:
        topology = parse_logical_topology(
            provider_cfg,
            profile_ids=profile_ids,
            implicit_profiles=[str(p.get("id")) for p in profiles if p.get("id")],
        )
    except Exception as exc:
        _store_error(
            ctx,
            "config",
            {"error": str(exc), "kind": "agent_isolation_invalid"},
            kind="agent_isolation_invalid",
        )
        return False
    if topology is None:
        _store_error(
            ctx,
            "config",
            {"error": "missing agent topology"},
            kind="agent_isolation_invalid",
        )
        return False
    ctx.topology = topology

    with timer.phase("prepare"):
        try:
            docker, runtime, l1_meta = prepare_l1_runtime(
                ctx.package_root,
                ctx.lock,
                ctx.run_dir,
                attempt=attempt,
                network_mode=network_mode,
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            kind = "target_prepare_failed"
            if "plugin_not_ready" in msg:
                kind = "plugin_not_ready"
            elif "image_contribute_unsatisfied" in msg:
                kind = "image_contribute_unsatisfied"
            _store_error(ctx, "provider", {"error": msg[:800], "kind": kind}, kind=kind)
            return False
        assert runtime.workdir_host is not None
        assert runtime.attempt is not None
        assert_same_attempt(attempt, runtime.attempt)
        ctx.docker = docker
        ctx.runtime = runtime
        ctx.l1_meta = l1_meta
        ctx.workspace_host = runtime.workdir_host / "workspace"
        seed_l1_workspace(
            package_root=ctx.package_root,
            workspace_host=ctx.workspace_host,
            allow_offline_agent=ctx.allow_offline_agent,
            l1_meta=l1_meta,
        )
        ctx.evidence_store = AttemptEvidenceStore(
            root=ctx.run_dir,
            attempt_id=attempt.value,
            run_id=attempt.trial.run.value,
            database_root=ctx.database_root or _database_root_for_run(ctx.run_dir),
        )
        with contextlib.suppress(Exception):
            lock_doc: dict[str, Any] = {
                "digest": ctx.lock.digest,
                "task_id": ctx.lock.task_id,
                "topology": topology.public_summary(),
                "profiles": [
                    {
                        "id": p.get("id"),
                        "executor": p.get("executor"),
                        "model": p.get("model"),
                        **(
                            {"options": {"entry": (p.get("options") or {}).get("entry")}}
                            if isinstance(p.get("options"), dict)
                            and (p.get("options") or {}).get("entry") is not None
                            else {}
                        ),
                    }
                    for p in profiles
                ],
            }
            if ctx.lock.provenance is not None:
                lock_doc["provenance"] = thaw(ctx.lock.provenance)
            if ctx.lock.job_overlay is not None:
                lock_doc["job_overlay"] = thaw(ctx.lock.job_overlay)
            ctx.evidence_store.write_lock_summary(lock_doc)

        cred = project_executor_credentials(work_root=runtime.workdir_host)
        ctx.cred = cred
        l1_meta["credential_projection"] = {
            "keys": list(cred.locator_keys),
            "has_material": cred.has_material,
        }
        l1_meta["isolation"] = topology.public_summary()
        l1_meta["scheduling"] = "sdk_session"
        l1_meta["residual_one_shot"] = False

        try:
            ledger = docker.prepare_agent_targets(
                runtime,
                topology,
                cred_root=cred.root,
                network_mode=network_mode,
            )
        except Exception as exc:  # noqa: BLE001
            _store_error(
                ctx,
                "provider",
                {**l1_meta, "prepare_error": type(exc).__name__, "message": str(exc)[:500]},
                kind="target_prepare_failed",
            )
            return False
        ctx.ledger = ledger
        l1_meta["targets"] = [t.public_view() for t in ledger.targets.values()]
        l1_meta["actors"] = [a.public_view() for a in ledger.actors.values()]

        def validate_actor_profile(actor_id: str, profile_id: str) -> dict[str, Any]:
            if not topology.allowed_profile(actor_id, profile_id):
                if topology.actor(actor_id) is None:
                    return {"ok": False, "error": "unknown_actor"}
                return {"ok": False, "error": "profile_not_allowed"}
            binding = ledger.actors.get(actor_id)
            if binding is None:
                return {"ok": False, "error": "unknown_actor"}
            target = ledger.targets.get(binding.target_id)
            if target is None or target.state != "ready":
                return {"ok": False, "error": "target_dead"}
            return {
                "ok": True,
                "target_id": binding.target_id,
                "generation": binding.generation,
            }

        resolve_placement = make_l1_placement_resolver(ledger=ledger)
        try:
            inv_limit = int(thaw(ctx.lock.limits).get("agent_invocations") or 1)
        except Exception:
            inv_limit = 1
        wall_s, deadline = read_wall_deadline(ctx.lock, monotonic_now=time.monotonic())
        ctx.wall_s = wall_s
        service, invoke_timeout, authority = assemble_parent_agent_service(
            profiles=profiles,
            package_root=ctx.package_root,
            attempt=attempt,
            inv_limit=inv_limit,
            params=params if isinstance(params, dict) else {},
            evidence_store=ctx.evidence_store,
            deadline_monotonic=deadline,
            workdir=ctx.workspace_host,
            require_actor_id=True,
            validate_actor_profile=validate_actor_profile,
            resolve_placement=resolve_placement,
            l1_container_only=True,
        )
        ctx.agent_service = service
        ctx.authority = authority
        sock = Path(tempfile.gettempdir()) / f"bora-ags-{attempt.trial.run.value[:12]}.sock"
        ctx.agent_sock_path = sock
        ctx.agent_server = AgentServiceServer(service, sock)
        ctx.agent_server.start()
        ctx.agent_meta = {
            **ctx.agent_meta,
            "mode": "parent_agent_service_l1",
            "attempt_id": attempt.value,
            "trial_id": attempt.trial.value,
            "run_id": attempt.trial.run.value,
            "executor_containment": "attempt-container",
            "scheduling": "sdk_session",
            "invoke_timeout_seconds": invoke_timeout,
            "wall_time_seconds": wall_s if wall_s > 0 else None,
        }
    return True


async def run_l1_harness(ctx: AttemptStageContext) -> None:
    from bora.application.run_harness import run_harness_package
    from bora.config.shared import infer_database_root_from_task

    timer = _timer(ctx)
    attempt = _attempt(ctx)
    params = thaw(ctx.lock.parameters)
    try:
        with timer.phase("run"):
            harness_timeout = float(params.get("harness_timeout_seconds") or 360.0)
            if ctx.wall_s > 0:
                harness_timeout = min(harness_timeout, ctx.wall_s)
            ctx.harness_out = await run_harness_package(
                ctx.lock,
                ctx.package_root,
                timeout_seconds=harness_timeout,
                agent_service_sock=str(ctx.agent_sock_path) if ctx.agent_sock_path else None,
                attempt=attempt,
                workspace_root=ctx.workspace_host,
                database_root=ctx.database_root or infer_database_root_from_task(ctx.package_root),
            )
    finally:
        if ctx.agent_server is not None:
            ctx.agent_server.stop()
            ctx.agent_server = None
        if ctx.agent_service is not None:
            ctx.inv_count = ctx.agent_service.invocations_completed
            ctx.agent_meta["invocations"] = ctx.inv_count


def seal_l1_inputs(ctx: AttemptStageContext) -> bool:
    envelope = ctx.harness_out.get("envelope") or {}
    ctx.envelope = envelope if isinstance(envelope, dict) else {}
    harness_kind = "completed" if ctx.envelope.get("ok") else "failed"
    if ctx.envelope.get("terminal") and isinstance(ctx.envelope["terminal"], dict):
        harness_kind = str(ctx.envelope["terminal"].get("kind") or harness_kind)
    ctx.harness_kind = harness_kind

    published = ctx.envelope.get("published") or {}
    hold = ctx.harness_out.get("artifact_hold")
    staging = ctx.run_dir / "eval_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    eval_inputs = thaw(ctx.lock.evaluation).get("inputs") or []
    artifact_filename = "session-output.json"
    artifact_key = "session-output"
    if isinstance(eval_inputs, list) and eval_inputs:
        first = eval_inputs[0]
        if isinstance(first, dict):
            artifact_key = str(first.get("artifact") or artifact_key)
            target = str(first.get("target") or f"artifacts/{artifact_key}.json")
            artifact_filename = Path(target).name

    src_art: Path | None = None
    if isinstance(published, dict) and artifact_key in published:
        cand = Path(str(published[artifact_key]))
        if cand.is_file():
            src_art = cand
    if src_art is None and hold:
        hold_path = Path(str(hold))
        for p in hold_path.glob(f"{artifact_key}*"):
            if p.is_file():
                src_art = p
                break
    if src_art is None or not src_art.is_file():
        _store_error(
            ctx,
            "harness" if not ctx.envelope.get("ok") else "evaluation_input",
            {**ctx.l1_meta, "harness": ctx.envelope},
            inv=ctx.inv_count,
        )
        return False

    (staging / artifact_filename).write_bytes(src_art.read_bytes())
    eval_py = ctx.package_root / "evaluator.py"
    if eval_py.is_file():
        (staging / "evaluator.py").write_bytes(eval_py.read_bytes())
    expected_filename: str | None = None
    expected_host = ctx.package_root / "evaluation" / "expected.json"
    if expected_host.is_file():
        (staging / "expected.json").write_bytes(expected_host.read_bytes())
        expected_filename = "expected.json"
    ctx.artifacts_map = {
        "artifact_filename": artifact_filename,
        "artifact_key": artifact_key,
        "src": str(src_art),
        **({"expected_filename": expected_filename} if expected_filename else {}),
    }

    runtime = ctx.runtime
    if runtime is None or not runtime.writer_stop_confirmed:
        _store_error(
            ctx,
            "evaluation_input",
            {**ctx.l1_meta, "error_kind": "residual_writer", "writer_stop_confirmed": False},
            kind="residual_writer",
            inv=ctx.inv_count,
        )
        return False
    return True


def evaluate_l1(ctx: AttemptStageContext) -> None:
    from bora.application.extension_hooks import (
        hook_evaluation_input,
        hook_evaluation_runtime,
        hook_score_postprocess,
    )

    timer = _timer(ctx)
    runtime = ctx.runtime
    assert runtime is not None
    artifact_key = ctx.artifacts_map.get("artifact_key") or "session-output"
    artifact_filename = ctx.artifacts_map.get("artifact_filename") or "session-output.json"
    expected_filename = ctx.artifacts_map.get("expected_filename")
    src_art = Path(ctx.artifacts_map["src"])
    staging = ctx.run_dir / "eval_staging"

    with timer.phase("evaluate"):
        contrib = hook_evaluation_input(
            ctx.lock,
            {
                "artifacts": {artifact_key: str(src_art)},
                "staging": str(staging),
                "package_root": str(ctx.package_root),
                "artifact_key": artifact_key,
                "artifact_filename": artifact_filename,
            },
        )
        if isinstance(contrib, dict):
            extra_arts = contrib.get("artifacts")
            if isinstance(extra_arts, dict):
                for _k, v in extra_arts.items():
                    p = Path(str(v))
                    if p.is_file():
                        dest = staging / p.name
                        if not dest.exists():
                            dest.write_bytes(p.read_bytes())
        runtime_ann = hook_evaluation_runtime(ctx.lock, {"source": "package", "path": "run_l1"})
        if runtime_ann is not None:
            ctx.l1_meta["evaluation_runtime"] = (
                dict(runtime_ann) if isinstance(runtime_ann, dict) else {"value": runtime_ann}
            )
        eval_raw, eval_meta = run_clean_evaluator_container(
            image_tag=runtime.image_lock.image_tag if runtime.image_lock else "bora-attempt:l1",
            staging=staging,
            artifact_filename=artifact_filename,
            artifact_key=artifact_key,
            expected_filename=expected_filename,
        )
        if isinstance(eval_raw, dict):
            eval_raw = hook_score_postprocess(ctx.lock, eval_raw)
            if not isinstance(eval_raw, dict):
                raise RuntimeError("score_postprocess_must_return_dict")
        ctx.evaluator_raw = eval_raw
        ctx.eval_meta = eval_meta
        ctx.l1_meta["evaluator"] = eval_meta
        ctx.l1_meta["writer_inventory"] = list(runtime.writer_inventory)
        ctx.l1_meta["writer_stop_confirmed"] = runtime.writer_stop_confirmed and bool(
            eval_meta.get("writer_stop_confirmed")
        )
        ctx.l1_meta["executor_containment"] = "attempt-container"
        ctx.l1_meta["execution_location"] = "attempt-container"


def bind_l1_result(ctx: AttemptStageContext) -> None:
    timer = _timer(ctx)
    eval_raw = ctx.evaluator_raw
    eval_meta = ctx.eval_meta
    full_l1 = bool(
        ctx.harness_kind == "completed"
        and eval_meta.get("ok")
        and eval_meta.get("writer_stop_confirmed")
        and (ctx.inv_count >= 1 or bool(ctx.l1_meta.get("solution_seed")))
    )
    db_root = ctx.database_root or _database_root_for_run(ctx.run_dir)
    locator = portable_run_locator(ctx.run_dir, database_root=db_root)
    flat = bind_result(
        evaluator_raw=eval_raw,
        harness_kind=ctx.harness_kind,
        runtime_kind="docker_l1",
        agent_invocations=ctx.inv_count,
        evidence_path=locator,
        error_phase=None
        if eval_raw and eval_raw.get("status") in {"PASS", "FAIL"}
        else "evaluation",
        logs=locator,
    )
    doc = flat.as_dict()
    doc["assurance"] = "l1" if full_l1 else "l0"
    doc["l1"] = {**ctx.l1_meta, "full_l1": full_l1}
    details = {
        "agent": ctx.agent_meta,
        "harness": ctx.envelope,
        "l1": doc["l1"],
        "assurance": doc["assurance"],
        "run_dir": locator,
        "logs": locator,
        "digest": ctx.lock.digest,
    }
    timing = timer.as_dict()
    doc["phase_timing"] = timing
    doc["duration"] = format_duration_ms(timing.get("total_ms"))  # type: ignore[arg-type]
    details = {**details, "phase_timing": timing}
    write_l1_evidence(ctx.run_dir, doc, ctx.agent_meta, doc["l1"], database_root=db_root)
    code = 0 if flat.status == "PASS" else (1 if flat.status == "FAIL" else 2)
    if ctx.allow_offline_agent and ctx.inv_count == 0 and not ctx.envelope.get("ok"):
        code = 2
    ctx.exit_code = code
    ctx.result_doc = doc
    ctx.details = details


def cleanup_l1(ctx: AttemptStageContext) -> None:
    _l1_host_cleanup(
        ctx.docker,
        ctx.runtime,
        ctx.cred,
        ctx.run_dir,
        keep_workspace=ctx.keep_workspace,
    )
