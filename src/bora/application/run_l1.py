"""Full L1 Attempt orchestration (Spec 07).

Containment rules:
- Harness container: network none, filtered package (no evaluation/), no credentials.
- Agent Executor container: optional bridge network + credential projection only;
  workspace-only write; filtered package; never evaluation/.
- Clean evaluator container: staging only, network none, no package mount, no creds.
- assurance:l1 only when harness + agent (if any) + evaluator writers confirmed and
  isolation probes pass.

Helpers live in sibling modules: prepare · evaluator · evidence (chore #31).
"""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path
from typing import Any

from bora.adapters.credential_projection import project_executor_credentials
from bora.application.phase_timing import PhaseTimer, format_duration_ms
from bora.application.run_l1_evaluator import run_clean_evaluator_container
from bora.application.run_l1_evidence import l1_error_result, write_l1_evidence
from bora.application.run_l1_prepare import (
    make_l1_target_executor_factory,
    prepare_l1_runtime,
    seed_l1_workspace,
)


def _attach_timing(
    doc: dict[str, Any],
    details: dict[str, Any],
    timer: PhaseTimer,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Stamp phase_timing onto result doc + details (and duration label)."""
    timing = timer.as_dict()
    doc = dict(doc)
    doc["phase_timing"] = timing
    doc["duration"] = format_duration_ms(timing.get("total_ms"))  # type: ignore[arg-type]
    details = {**details, "phase_timing": timing}
    return doc, details


def run_l1_attempt(
    *,
    package_root: Path,
    lock: Any,
    run_dir: Path,
    agent_meta: dict[str, Any],
    allow_offline_agent: bool,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Dispatch L1 SDK session path when agent_profiles is non-empty.

    Isolation (hidden gold, credential/network projection, writer-stop) is enforced
    by Provider prepare/run and the SDK session barrier — not by Application
    task_id/probe special cases. Provider contract tests live under tests/provider_l1/.
    """
    from bora.config.model import thaw

    task_id = str(lock.task_id)
    profiles = [p for p in thaw(lock.agent_profiles) if isinstance(p, dict)]

    if profiles:
        return run_l1_sdk_session_attempt(
            package_root=package_root,
            lock=lock,
            run_dir=run_dir,
            agent_meta=agent_meta,
            allow_offline_agent=allow_offline_agent,
        )

    return l1_error_result(
        run_dir,
        "config",
        {"error": "l1_dispatch_unsupported", "task_id": task_id},
        agent_meta,
        0,
        kind="l1_dispatch_unsupported",
    )


def run_l1_sdk_session_attempt(
    *,
    package_root: Path,
    lock: Any,
    run_dir: Path,
    agent_meta: dict[str, Any],
    allow_offline_agent: bool,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """L1 multi-actor SDK path: ParentAgentService → docker exec targets.

    Harness runs as host task worker (same as L0 session path) with scoped
    agent service socket. All Agent CLI effects execute inside prepared targets.
    Agent effects are scheduled only from package harness via Agent.session/invoke.
    """
    import asyncio
    import tempfile
    import time

    from bora.application.run_harness import run_harness_package
    from bora.config.model import thaw
    from bora.evaluation.result_binding import bind_result
    from bora.evidence.store import AttemptEvidenceStore
    from bora.provider.isolation import parse_logical_topology
    from bora.runtime.agent_service_protocol import AgentServiceServer
    from bora.runtime.parent_agent_service import ParentAgentService

    package_root = package_root.resolve()
    timer = PhaseTimer()
    params = thaw(lock.parameters)
    profiles = [p for p in thaw(lock.agent_profiles) if isinstance(p, dict)]
    provider_cfg = thaw(lock.provider) if hasattr(lock, "provider") else {}
    if not isinstance(provider_cfg, dict):
        provider_cfg = {}
    network_mode = str(provider_cfg.get("network") or "bridge")

    profile_ids = {str(p.get("id")) for p in profiles if p.get("id")}
    # Explicit topology or Phase-0 implicit single actor.
    try:
        topology = parse_logical_topology(
            provider_cfg,
            profile_ids=profile_ids,
            implicit_profiles=[str(p.get("id")) for p in profiles if p.get("id")],
        )
    except Exception as exc:  # ConfigError or validation
        return l1_error_result(
            run_dir,
            "config",
            {"error": str(exc), "kind": "agent_isolation_invalid"},
            agent_meta,
            0,
            kind="agent_isolation_invalid",
            phase_timing=timer.as_dict(),
        )
    if topology is None:
        return l1_error_result(
            run_dir,
            "config",
            {"error": "missing agent topology"},
            agent_meta,
            0,
            kind="agent_isolation_invalid",
            phase_timing=timer.as_dict(),
        )

    with timer.phase("prepare"):
        docker, runtime, l1_meta = prepare_l1_runtime(
            package_root, lock, run_dir, network_mode=network_mode
        )
        assert runtime.workdir_host is not None
        assert runtime.attempt is not None

        workspace_host = runtime.workdir_host / "workspace"
        seed_l1_workspace(
            package_root=package_root,
            workspace_host=workspace_host,
            allow_offline_agent=allow_offline_agent,
            l1_meta=l1_meta,
        )

        # Reuse prepare attempt identity for ParentAgentService + harness.
        attempt_ident = runtime.attempt
        run_ident = attempt_ident.trial.run
        trial_ident = attempt_ident.trial

        evidence_store = AttemptEvidenceStore(
            root=run_dir,
            attempt_id=attempt_ident.value,
            run_id=run_ident.value,
        )
        with contextlib.suppress(Exception):
            from bora.config.model import thaw as _thaw_lock

            lock_doc: dict[str, Any] = {
                "digest": lock.digest,
                "task_id": lock.task_id,
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
            if lock.provenance is not None:
                lock_doc["provenance"] = _thaw_lock(lock.provenance)
            if lock.job_overlay is not None:
                lock_doc["job_overlay"] = _thaw_lock(lock.job_overlay)
            evidence_store.write_lock_summary(lock_doc)

        cred = project_executor_credentials(work_root=runtime.workdir_host)
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
            docker.cleanup(runtime)
            cred.cleanup()
            return l1_error_result(
                run_dir,
                "provider",
                {**l1_meta, "prepare_error": type(exc).__name__, "message": str(exc)[:500]},
                agent_meta,
                0,
                kind="target_prepare_failed",
                phase_timing=timer.as_dict(),
            )

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

        make_target_executor = make_l1_target_executor_factory(ledger=ledger, profiles=profiles)

        limits: dict[str, Any] = {}
        try:
            raw_limits = thaw(lock.limits) if hasattr(lock, "limits") else {}
            if isinstance(raw_limits, dict):
                limits = raw_limits
        except Exception:
            limits = {}
        try:
            inv_limit = int(limits.get("agent_invocations") or 1)
        except Exception:
            inv_limit = 1
        try:
            wall_s = float(limits.get("wall_time_seconds") or 0)
        except Exception:
            wall_s = 0.0
        deadline = (time.monotonic() + wall_s) if wall_s > 0 else None

        from bora.plugins.bootstrap import ensure_bootstrapped

        agent_service = ParentAgentService(
            profiles=profiles,
            agent_invocation_limit=inv_limit,
            attempt_id=attempt_ident.value,
            extension_registry=ensure_bootstrapped(),
            evidence_store=evidence_store,
            deadline_monotonic=deadline,
            require_actor_id=True,
            validate_actor_profile=validate_actor_profile,
            make_target_executor=make_target_executor,
            l1_container_only=True,
        )
        short = Path(tempfile.gettempdir()) / f"bora-ags-{run_ident.value[:12]}.sock"
        agent_server = AgentServiceServer(agent_service, short)
        agent_server.start()

        agent_meta = {
            **agent_meta,
            "mode": "parent_agent_service_l1",
            "attempt_id": attempt_ident.value,
            "trial_id": trial_ident.value,
            "run_id": run_ident.value,
            "executor_containment": "attempt-container",
            "scheduling": "sdk_session",
        }

    try:
        with timer.phase("run"):
            harness_timeout = float(params.get("harness_timeout_seconds") or 360.0)
            if wall_s > 0:
                harness_timeout = min(harness_timeout, wall_s)
            harness_coro = run_harness_package(
                lock,
                package_root,
                timeout_seconds=harness_timeout,
                agent_service_sock=str(short),
                attempt=attempt_ident,
                workspace_root=workspace_host,
            )
            # run_task is already async; nest safely without asyncio.run in-loop.
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                harness_out = asyncio.run(harness_coro)
            else:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    harness_out = pool.submit(asyncio.run, harness_coro).result()
    finally:
        agent_server.stop()
        inv_count = agent_service.invocations_completed
        agent_meta["invocations"] = inv_count
        agent_meta["host_fallback_count"] = (
            agent_service.host_fallback_count + ledger.host_fallback_count
        )
        docker.stop_agent_targets(runtime)

    envelope = harness_out.get("envelope") or {}
    harness_kind = "completed" if envelope.get("ok") else "failed"
    if envelope.get("terminal") and isinstance(envelope["terminal"], dict):
        harness_kind = str(envelope["terminal"].get("kind") or harness_kind)

    # Materialize published artifacts for clean evaluator.
    with timer.phase("evaluate"):
        published = envelope.get("published") or {}
        hold = harness_out.get("artifact_hold")
        staging = run_dir / "eval_staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        eval_inputs = thaw(lock.evaluation).get("inputs") or []
        artifact_filename = "session-output.json"
        artifact_key = "session-output"
        if isinstance(eval_inputs, list) and eval_inputs:
            first = eval_inputs[0]
            if isinstance(first, dict):
                artifact_key = str(first.get("artifact") or artifact_key)
                target = str(first.get("target") or f"artifacts/{artifact_key}.json")
                artifact_filename = Path(target).name

        # Copy from durable hold (run_harness rewrites published to hold paths).
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
            with timer.phase("cleanup"):
                docker.cleanup(runtime)
                cred.cleanup()
            return l1_error_result(
                run_dir,
                "harness" if not envelope.get("ok") else "evaluation_input",
                {
                    **l1_meta,
                    "harness": envelope,
                    "host_fallback_count": agent_meta.get("host_fallback_count", 0),
                },
                agent_meta,
                inv_count,
                phase_timing=timer.as_dict(),
            )

        (staging / artifact_filename).write_bytes(src_art.read_bytes())
        eval_py = package_root / "evaluator.py"
        if eval_py.is_file():
            (staging / "evaluator.py").write_bytes(eval_py.read_bytes())
        # Gold materialize for terminal-class packages (never mounted during harness).
        expected_filename: str | None = None
        expected_host = package_root / "evaluation" / "expected.json"
        if expected_host.is_file():
            (staging / "expected.json").write_bytes(expected_host.read_bytes())
            expected_filename = "expected.json"

        # Wait for writer stop before evaluator.
        if not runtime.writer_stop_confirmed:
            with timer.phase("cleanup"):
                docker.cleanup(runtime)
                cred.cleanup()
            return l1_error_result(
                run_dir,
                "evaluation_input",
                {
                    **l1_meta,
                    "error_kind": "residual_writer",
                    "writer_stop_confirmed": False,
                },
                agent_meta,
                inv_count,
                kind="residual_writer",
                phase_timing=timer.as_dict(),
            )

        eval_raw, eval_meta = run_clean_evaluator_container(
            image_tag=runtime.image_lock.image_tag if runtime.image_lock else "bora-attempt:l1",
            staging=staging,
            artifact_filename=artifact_filename,
            artifact_key=artifact_key,
            expected_filename=expected_filename,
        )
        l1_meta["evaluator"] = eval_meta
        l1_meta["writer_inventory"] = list(runtime.writer_inventory)
        l1_meta["writer_stop_confirmed"] = runtime.writer_stop_confirmed and bool(
            eval_meta.get("writer_stop_confirmed")
        )
        l1_meta["host_fallback_count"] = int(agent_meta.get("host_fallback_count") or 0)
        l1_meta["executor_containment"] = "attempt-container"
        l1_meta["execution_location"] = "attempt-container"

    with timer.phase("cleanup"):
        docker.cleanup(runtime)
        cred.cleanup()

    full_l1 = bool(
        harness_kind == "completed"
        and eval_meta.get("ok")
        and eval_meta.get("writer_stop_confirmed")
        and l1_meta["host_fallback_count"] == 0
        and (inv_count >= 1 or bool(l1_meta.get("solution_seed")))
    )
    flat = bind_result(
        evaluator_raw=eval_raw,
        harness_kind=harness_kind,
        runtime_kind="docker_l1",
        agent_invocations=inv_count,
        evidence_path=str(run_dir),
        error_phase=None
        if eval_raw and eval_raw.get("status") in {"PASS", "FAIL"}
        else "evaluation",
    )
    doc = flat.as_dict()
    doc["assurance"] = "l1" if full_l1 else "l0"
    doc["l1"] = {**l1_meta, "full_l1": full_l1}
    details = {
        "agent": agent_meta,
        "harness": envelope,
        "l1": doc["l1"],
        "assurance": doc["assurance"],
        "run_dir": str(run_dir),
        "digest": lock.digest,
        "host_fallback_count": l1_meta["host_fallback_count"],
    }
    doc, details = _attach_timing(doc, details, timer)
    # Single write: write_l1_evidence copies phase_timing into summary.json.
    write_l1_evidence(run_dir, doc, agent_meta, doc["l1"])
    code = 0 if flat.status == "PASS" else (1 if flat.status == "FAIL" else 2)
    # Offline path: expected failure for real-agent smoke when offline.
    if allow_offline_agent and inv_count == 0 and not envelope.get("ok"):
        code = 2
    return code, doc, details
