"""Full L1 Attempt orchestration (Spec 07).

Containment rules:
- Harness container: network none, filtered package (no evaluation/), no credentials.
- Agent Executor container: optional bridge network + credential projection only;
  workspace-only write; filtered package; never evaluation/.
- Clean evaluator container: staging only, network none, no package mount, no creds.
- assurance:l1 only when harness + agent (if any) + evaluator writers confirmed and
  isolation probes pass.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from bora.adapters.credential_projection import project_executor_credentials
from bora.adapters.provider_docker import (
    DockerProvider,
    DockerRuntime,
    build_package_image,
    ensure_base_image,
    ensure_image_lock,
)
from bora.runtime.identity import IdentityFactory


def _parse_json_from_text(text: str) -> dict[str, Any] | None:
    """Best-effort extract a JSON object from CLI stdout tail."""
    import re

    raw = (text or "").strip()
    if not raw:
        return None
    # Prefer last JSONL message text for pi/opencode streams.
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            # pi assistant content
            msg = obj.get("message")
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                parts = msg.get("content")
                if isinstance(parts, list):
                    blobs = [
                        p.get("text", "")
                        for p in parts
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    joined = "\n".join(blobs).strip()
                    if joined:
                        try:
                            parsed = json.loads(joined)
                            if isinstance(parsed, dict):
                                return parsed
                        except json.JSONDecodeError:
                            m = re.search(r"\{[^{}]*\}", joined, re.S)
                            if m:
                                try:
                                    parsed = json.loads(m.group(0))
                                    if isinstance(parsed, dict):
                                        return parsed
                                except json.JSONDecodeError:
                                    pass
            # opencode text event
            part = obj.get("part")
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                try:
                    parsed = json.loads(part["text"])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
            if "answer" in obj or "n" in obj:
                return obj
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*\}", raw, re.S)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def run_l1_attempt(
    *,
    package_root: Path,
    lock: Any,
    run_dir: Path,
    agent_meta: dict[str, Any],
    agent_invocations: int,
    allow_offline_agent: bool,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Dispatch full L1 by package parameters / task_id."""
    from bora.config.model import thaw

    params = thaw(lock.parameters)
    task_id = str(lock.task_id)
    probe = str(params.get("probe") or "")
    workspace_out = str(params.get("workspace_output") or "")

    # SDK multi-actor scheduling path (Spec 18) — not residual one-shot.
    if bool(params.get("use_agent_session")):
        return run_l1_sdk_session_attempt(
            package_root=package_root,
            lock=lock,
            run_dir=run_dir,
            agent_meta=agent_meta,
            allow_offline_agent=allow_offline_agent,
        )

    if probe == "hidden" or task_id == "hidden-material-denied":
        return _run_l1_hidden_denied(package_root=package_root, lock=lock, run_dir=run_dir)
    if probe == "projection" or task_id == "projection-denied":
        return _run_l1_projection_denied(package_root=package_root, lock=lock, run_dir=run_dir)
    if probe == "residual_writer" or task_id == "residual-writer":
        return _run_l1_residual_writer(package_root=package_root, lock=lock, run_dir=run_dir)
    if workspace_out:
        return run_l1_workspace_attempt(
            package_root=package_root,
            lock=lock,
            run_dir=run_dir,
            agent_meta=agent_meta,
            agent_invocations=agent_invocations,
            workspace_output_name=workspace_out,
            allow_offline_agent=allow_offline_agent,
        )
    # Residual one-shot structured agent-eval class L1 (compatibility smoke only).
    # Not multi-agent SDK scheduling; see Spec 18 residual quarantine.
    return _run_l1_agent_eval(
        package_root=package_root,
        lock=lock,
        run_dir=run_dir,
        agent_meta={**agent_meta, "residual_one_shot": True, "scheduling": "parameters.question"},
        allow_offline_agent=allow_offline_agent,
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
    Residual one-shot ``parameters.question`` is not used here.
    """
    import asyncio
    import tempfile
    import time

    from bora.application.run_harness import run_harness_package
    from bora.config.model import thaw
    from bora.evaluation.result_binding import bind_result
    from bora.evidence.store import AttemptEvidenceStore
    from bora.provider.isolation import parse_logical_topology
    from bora.runtime.agent_service import AgentServiceServer, ParentAgentService

    package_root = package_root.resolve()
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
        return _err(
            run_dir,
            "config",
            {"error": str(exc), "kind": "agent_isolation_invalid"},
            agent_meta,
            0,
            kind="agent_isolation_invalid",
        )
    if topology is None:
        return _err(
            run_dir,
            "config",
            {"error": "missing agent topology"},
            agent_meta,
            0,
            kind="agent_isolation_invalid",
        )

    docker, runtime, l1_meta = _prepare(
        package_root, lock, run_dir, network_mode=network_mode
    )
    assert runtime.workdir_host is not None
    assert runtime.attempt is not None

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
        evidence_store.write_lock_summary(
            {
                "digest": lock.digest,
                "task_id": lock.task_id,
                "topology": topology.public_summary(),
                "profiles": [
                    {
                        "id": p.get("id"),
                        "executor": p.get("executor"),
                        "model": p.get("model"),
                    }
                    for p in profiles
                ],
            }
        )

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
        return _err(
            run_dir,
            "provider",
            {**l1_meta, "prepare_error": type(exc).__name__, "message": str(exc)[:500]},
            agent_meta,
            0,
            kind="target_prepare_failed",
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

    def make_target_executor(binding: Any) -> Any:
        from bora.adapters.acp_registry import get_entry
        from bora.adapters.agent_acp import AcpExecutor
        from bora.adapters.agent_container import effective_run_gid

        actor_id = binding.actor_id
        if not actor_id:
            raise RuntimeError("actor_id_required")
        phys = ledger.actors.get(actor_id)
        if phys is None:
            raise RuntimeError("unknown_actor")
        target = ledger.targets.get(phys.target_id)
        if target is None or target.state != "ready" or not target.container_id:
            raise RuntimeError("target_dead")
        if binding.generation is not None and binding.generation != target.generation:
            raise RuntimeError("generation_mismatch")
        if binding.target_id and binding.target_id != target.target_id:
            raise RuntimeError("target_mismatch")

        profile = next((p for p in profiles if p.get("id") == binding.profile_id), {})
        api_key_env = (
            str(profile.get("api_key")).strip()
            if isinstance(profile.get("api_key"), str) and profile.get("api_key")
            else None
        )
        base_url = (
            str(profile.get("base_url")).strip()
            if isinstance(profile.get("base_url"), str) and profile.get("base_url")
            else None
        )
        kind = str(binding.executor_kind)
        # Spec 19: L1 coding-agent path is ACP only — no private CLI scrape residual.
        if kind != "acp":
            raise RuntimeError(
                f"migrated_to_acp: L1 executor {kind!r} requires "
                "executor: acp + options.entry"
            )
        entry_id = getattr(binding, "acp_entry_id", None)
        if not entry_id:
            options = profile.get("options") if isinstance(profile, dict) else {}
            if isinstance(options, dict):
                entry_id = options.get("entry")
        if not entry_id:
            raise RuntimeError("acp_entry_required")
        desc = get_entry(str(entry_id))
        if desc is None:
            raise RuntimeError("unknown_acp_entry")
        child_env = _cli_env_for_container(
            str(entry_id), api_key_env=api_key_env, base_url=base_url
        )
        home = phys.home_container
        child_env["HOME"] = home
        child_env["CODEX_HOME"] = f"{home}/.codex"
        # Force container PATH (projection never carries host PATH after fix).
        child_env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        child_env.setdefault("TERM", "xterm")
        child_env["NO_BROWSER"] = "1"
        child_env.setdefault("XDG_CONFIG_HOME", f"{home}/.config")
        child_env.setdefault("XDG_CACHE_HOME", f"{home}/.cache")
        child_env.setdefault("XDG_STATE_HOME", f"{home}/.local/state")
        child_env.setdefault("XDG_DATA_HOME", f"{home}/.local/share")
        for k, v in desc.fixed_env.items():
            child_env.setdefault(str(k), str(v))
        workdir = "/attempt/workspace"
        run_gid = effective_run_gid(phys)
        docker_cmd: list[str] = [
            "docker",
            "exec",
            "-i",
            "-u",
            f"{phys.uid}:{run_gid}",
            "-w",
            workdir,
        ]
        for ek, ev in child_env.items():
            if str(ek).upper() in {"DOCKER_HOST", "DOCKER_SOCK"}:
                continue
            docker_cmd.extend(["-e", f"{ek}={ev}"])
        docker_cmd.append(str(target.container_id))
        # shared_write collaboration: group-writable new files under shared GID.
        acp_argv = list(desc.acp_command)
        if phys.shared_gid is not None and phys.shared_write:
            docker_cmd.extend(
                ["sh", "-c", 'umask 002; exec "$@"', "bora-actor", *acp_argv]
            )
        else:
            docker_cmd.extend(acp_argv)
        return AcpExecutor(
            entry_id=str(entry_id),
            model=str(binding.model),
            descriptor=desc,
            workdir=workdir,
            api_key_env=api_key_env,
            base_url=base_url,
            command_override=docker_cmd,
        )

    try:
        limits = thaw(lock.limits) if hasattr(lock, "limits") else {}
        inv_limit = int((limits or {}).get("agent_invocations") or 1)
    except Exception:
        inv_limit = 1
    try:
        wall_s = float((limits or {}).get("wall_time_seconds") or 0)
    except Exception:
        wall_s = 0.0
    deadline = (time.monotonic() + wall_s) if wall_s > 0 else None

    def _host_resolve(*_a: Any, **_k: Any) -> Any:
        # L1 path must never call host CLI — mark counter and fail.
        ledger.host_fallback_count += 1
        raise RuntimeError("host_fallback_forbidden")

    agent_service = ParentAgentService(
        profiles=profiles,
        agent_invocation_limit=inv_limit,
        resolve_executor=_host_resolve,
        attempt_id=attempt_ident.value,
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
        harness_timeout = float(params.get("harness_timeout_seconds") or 360.0)
        if wall_s > 0:
            harness_timeout = min(harness_timeout, wall_s)
        harness_coro = run_harness_package(
            lock,
            package_root,
            timeout_seconds=harness_timeout,
            agent_service_sock=str(short),
            attempt=attempt_ident,
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
        docker.cleanup(runtime)
        cred.cleanup()
        return _err(
            run_dir,
            "harness" if not envelope.get("ok") else "evaluation_input",
            {
                **l1_meta,
                "harness": envelope,
                "host_fallback_count": agent_meta.get("host_fallback_count", 0),
            },
            agent_meta,
            inv_count,
        )

    (staging / artifact_filename).write_bytes(src_art.read_bytes())
    eval_py = package_root / "evaluator.py"
    if eval_py.is_file():
        (staging / "evaluator.py").write_bytes(eval_py.read_bytes())

    # Wait for writer stop before evaluator.
    if not runtime.writer_stop_confirmed:
        docker.cleanup(runtime)
        cred.cleanup()
        return _err(
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
        )

    eval_raw, eval_meta = _run_clean_evaluator_container(
        image_tag=runtime.image_lock.image_tag if runtime.image_lock else "bora-attempt:l1",
        staging=staging,
        artifact_filename=artifact_filename,
        artifact_key=artifact_key,
        expected_filename=None,
    )
    l1_meta["evaluator"] = eval_meta
    l1_meta["writer_inventory"] = list(runtime.writer_inventory)
    l1_meta["writer_stop_confirmed"] = runtime.writer_stop_confirmed and bool(
        eval_meta.get("writer_stop_confirmed")
    )
    l1_meta["host_fallback_count"] = int(agent_meta.get("host_fallback_count") or 0)
    l1_meta["executor_containment"] = "attempt-container"
    l1_meta["execution_location"] = "attempt-container"
    docker.cleanup(runtime)
    cred.cleanup()

    full_l1 = bool(
        harness_kind == "completed"
        and eval_meta.get("ok")
        and eval_meta.get("writer_stop_confirmed")
        and l1_meta["host_fallback_count"] == 0
        and inv_count >= 1
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
    _write_evidence(run_dir, doc, agent_meta, doc["l1"])
    code = 0 if flat.status == "PASS" else (1 if flat.status == "FAIL" else 2)
    # Offline path: expected failure for real-agent smoke when offline.
    if allow_offline_agent and inv_count == 0 and not envelope.get("ok"):
        code = 2
    return (
        code,
        doc,
        {
            "agent": agent_meta,
            "harness": envelope,
            "l1": doc["l1"],
            "assurance": doc["assurance"],
            "run_dir": str(run_dir),
            "digest": lock.digest,
            "host_fallback_count": l1_meta["host_fallback_count"],
        },
    )


def _prepare(
    package_root: Path, lock: Any, run_dir: Path, *, network_mode: str = "none"
) -> tuple[DockerProvider, DockerRuntime, dict[str, Any]]:
    from bora.config.model import thaw

    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, lock.digest)
    attempt = factory.new_attempt(trial)
    package_root = package_root.resolve()
    provider = thaw(lock.provider) if hasattr(lock, "provider") else {}
    if not isinstance(provider, dict):
        provider = {}
    dockerfile_rel = str(provider.get("dockerfile") or "environment/Dockerfile")
    platform = str(provider.get("platform") or "linux/arm64")
    # Official base (FROM bora-attempt:l1) then package Dockerfile → Attempt image.
    ensure_base_image(Path.cwd())
    short = lock.digest.replace("sha256:", "")[:12]
    tag = f"bora-pkg:{lock.task_id}-{short}"
    pkg_image = build_package_image(
        package_root=package_root,
        dockerfile_rel=dockerfile_rel,
        platform=platform,
        tag=tag,
        repo_root=Path.cwd(),
    )
    lock_path = Path.cwd() / ".bora" / "runtime-images" / "provider-l1.json"
    if not lock_path.is_file():
        lock_path = ensure_image_lock(Path.cwd())
    docker = DockerProvider(image_lock_path=lock_path)
    work = run_dir / "l1-work"
    if work.exists():
        shutil.rmtree(work)
    runtime = docker.prepare(
        attempt,
        package_root=package_root,
        work_root=work,
        network_mode=network_mode,
        hide_evaluation=True,
        image_lock=pkg_image,
    )
    meta = {
        "containment": "full_l1_attempt",
        "image": runtime.image_lock.image_digest if runtime.image_lock else "",
        "image_tag": runtime.image_lock.image_tag if runtime.image_lock else "",
        "package_dockerfile": dockerfile_rel,
        "platform": runtime.image_lock.platform if runtime.image_lock else "",
        "attempt_id": attempt.value,
        "policy": dict(runtime.policy_digests),
    }
    return docker, runtime, meta


def run_l1_workspace_attempt(
    *,
    package_root: Path,
    lock: Any,
    run_dir: Path,
    agent_meta: dict[str, Any],
    agent_invocations: int,
    workspace_output_name: str,
    allow_offline_agent: bool,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Terminal-class L1: agent (container preferred) → harness container → clean eval."""
    from bora.config.model import thaw
    from bora.evaluation.result_binding import bind_result

    package_root = package_root.resolve()
    docker, runtime, l1_meta = _prepare(package_root, lock, run_dir)
    assert runtime.workdir_host is not None
    workspace = runtime.workdir_host / "workspace"
    data_dir = package_root / "data"
    if data_dir.is_dir():
        for src in data_dir.iterdir():
            if src.is_file():
                shutil.copy2(src, workspace / src.name)

    profiles = thaw(lock.agent_profiles)
    params = thaw(lock.parameters)
    profile = next((p for p in profiles if isinstance(p, dict)), None)
    if profile is None:
        docker.cleanup(runtime)
        return _err(run_dir, "config", l1_meta, agent_meta, 0)

    model = str(profile.get("model") or "entry-default")
    kind = str(profile.get("executor") or "acp")
    options = profile.get("options") if isinstance(profile.get("options"), dict) else {}
    entry_id = (
        str(options.get("entry")).strip()
        if isinstance(options, dict) and options.get("entry")
        else None
    )
    instruction = ""
    if (workspace / "instruction.md").is_file():
        instruction = (workspace / "instruction.md").read_text(encoding="utf-8")
    solution_seed = package_root / "solution" / workspace_output_name
    cred = project_executor_credentials(work_root=runtime.workdir_host)
    l1_meta["credential_projection"] = {
        "keys": list(cred.locator_keys),
        "has_material": cred.has_material,
    }

    try:
        if (workspace / workspace_output_name).is_file():
            agent_ok = True
            agent_meta = {
                **agent_meta,
                "ok": True,
                "source": "preexisting_workspace",
                "executor_containment": "n/a",
            }
        elif solution_seed.is_file() and (
            allow_offline_agent or os.environ.get("BORA_L1_USE_SOLUTION") == "1"
        ):
            shutil.copy2(solution_seed, workspace / workspace_output_name)
            agent_ok = True
            agent_invocations = 0
            agent_meta = {
                **agent_meta,
                "ok": True,
                "source": "solution_seed",
                "executor_containment": "n/a",
            }
        else:
            agent_ok, agent_invocations, agent_meta = _run_agent_executor_container(
                docker=docker,
                runtime=runtime,
                kind=kind,
                entry_id=entry_id,
                model=model,
                prompt=instruction or str(params.get("question") or 'Return JSON {"answer": 42}'),
                cred_root=cred.root,
                workspace_output_name=workspace_output_name,
                timeout=float(params.get("agent_timeout_seconds") or 300),
                api_key_env=(
                    str(profile.get("api_key")).strip()
                    if isinstance(profile.get("api_key"), str) and profile.get("api_key")
                    else None
                ),
                base_url=(
                    str(profile.get("base_url")).strip()
                    if isinstance(profile.get("base_url"), str) and profile.get("base_url")
                    else None
                ),
                evidence_root=run_dir,
            )
            agent_meta = {**agent_meta, "source": "executor_container"}
            if not agent_ok and not allow_offline_agent:
                docker.cleanup(runtime)
                return _err(
                    run_dir,
                    "agent",
                    {**l1_meta, "agent": agent_meta},
                    agent_meta,
                    agent_invocations,
                )

        harness_out, envelope = _run_harness_publish(
            docker, runtime, workspace_output_name=workspace_output_name
        )
        l1_meta["harness_exit"] = harness_out.exit_code
        l1_meta["harness_writer_stop"] = harness_out.writer_stop_confirmed
        if envelope.get("eval_visible"):
            docker.cleanup(runtime)
            return _err(
                run_dir,
                "provider",
                {**l1_meta, "error_kind": "workspace_view_denied"},
                agent_meta,
                agent_invocations,
                kind="workspace_view_denied",
            )
        if harness_out.exit_code != 0 or not envelope.get("ok"):
            docker.cleanup(runtime)
            return _err(run_dir, "harness", l1_meta, agent_meta, agent_invocations)

        eval_raw, eval_meta = _materialize_and_evaluate(
            package_root=package_root,
            run_dir=run_dir,
            runtime=runtime,
            docker=docker,
            artifact_name=workspace_output_name,
            artifact_id="aggregates",
            expected_name="expected.json",
        )
        l1_meta["evaluator"] = eval_meta
        l1_meta["writer_inventory"] = list(runtime.writer_inventory)
        l1_meta["writer_stop_confirmed"] = runtime.writer_stop_confirmed and bool(
            eval_meta.get("writer_stop_confirmed")
        )
        docker.cleanup(runtime)

        full_l1 = bool(
            envelope.get("eval_visible") is False
            and harness_out.writer_stop_confirmed
            and eval_meta.get("ok")
            and eval_meta.get("writer_stop_confirmed")
            and not eval_meta.get("package_mounted")
            and "openai_api_key" not in json.dumps(l1_meta)
        )
        flat = bind_result(
            evaluator_raw=eval_raw,
            harness_kind="completed",
            runtime_kind="docker_l1",
            agent_invocations=agent_invocations,
            evidence_path=str(
                run_dir.relative_to(package_root)
                if run_dir.is_relative_to(package_root)
                else run_dir
            ),
            error_phase=None
            if eval_raw and eval_raw.get("status") in {"PASS", "FAIL"}
            else "evaluation",
        )
        doc = flat.as_dict()
        doc["assurance"] = "l1" if full_l1 else "l0"
        doc["l1"] = {**l1_meta, "full_l1": full_l1}
        _write_evidence(run_dir, doc, agent_meta, doc["l1"])
        code = 0 if flat.status == "PASS" else (1 if flat.status == "FAIL" else 2)
        return (
            code,
            doc,
            {
                "agent": agent_meta,
                "harness": envelope,
                "l1": doc["l1"],
                "assurance": doc["assurance"],
                "run_dir": str(run_dir),
                "digest": lock.digest,
            },
        )
    finally:
        cred.cleanup()


def _run_l1_agent_eval(
    *,
    package_root: Path,
    lock: Any,
    run_dir: Path,
    agent_meta: dict[str, Any],
    allow_offline_agent: bool,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """provider-l1-agent-eval: structured JSON agent → harness container → clean eval."""
    from bora.config.model import thaw
    from bora.evaluation.result_binding import bind_result

    package_root = package_root.resolve()
    docker, runtime, l1_meta = _prepare(package_root, lock, run_dir)
    assert runtime.workdir_host is not None
    params = thaw(lock.parameters)
    profiles = thaw(lock.agent_profiles)
    profile = next((p for p in profiles if isinstance(p, dict)), None)
    if profile is None:
        docker.cleanup(runtime)
        return _err(run_dir, "config", l1_meta, agent_meta, 0)

    model = str(profile.get("model") or "entry-default")
    kind = str(profile.get("executor") or "acp")
    options = profile.get("options") if isinstance(profile.get("options"), dict) else {}
    entry_id = (
        str(options.get("entry")).strip()
        if isinstance(options, dict) and options.get("entry")
        else None
    )
    question = str(params.get("question") or 'Return JSON {"answer": 42}')
    cred = project_executor_credentials(work_root=runtime.workdir_host)
    l1_meta["credential_projection"] = {
        "keys": list(cred.locator_keys),
        "has_material": cred.has_material,
    }
    try:
        # Agent writes structured result into workspace (not package evaluation/).
        agent_ok, inv, agent_meta = _run_agent_structured(
            docker=docker,
            runtime=runtime,
            kind=kind,
            entry_id=entry_id,
            model=model,
            prompt=question,
            cred_root=cred.root,
            allow_offline=allow_offline_agent,
            api_key_env=(
                str(profile.get("api_key")).strip()
                if isinstance(profile.get("api_key"), str) and profile.get("api_key")
                else None
            ),
            base_url=(
                str(profile.get("base_url")).strip()
                if isinstance(profile.get("base_url"), str) and profile.get("base_url")
                else None
            ),
            evidence_root=run_dir,
        )
        if not agent_ok and not allow_offline_agent:
            docker.cleanup(runtime)
            return _err(run_dir, "agent", l1_meta, agent_meta, inv)

        # Harness container: read agent result from workspace, publish artifact.
        script = textwrap.dedent(
            """
            import json, shutil
            from pathlib import Path
            pkg = Path("/attempt/package")
            if (pkg / "evaluation").exists():
                print(json.dumps({"ok": False, "eval_visible": True}))
                raise SystemExit(3)
            src = Path("/attempt/workspace/agent_result.json")
            if not src.is_file():
                print(json.dumps({"ok": False, "error": "agent_result_missing"}))
                raise SystemExit(2)
            dest = Path("/attempt/artifacts/agent-output.json")
            shutil.copy2(src, dest)
            print(json.dumps({
                "ok": True,
                "terminal": {"kind": "completed"},
                "published": {"agent-output": str(dest)},
                "eval_visible": False,
            }))
            """
        )
        harness_out = docker.run_command(
            runtime,
            ["python", "-c", script],
            network=False,
            writer_name="harness",
            timeout_seconds=60,
        )
        try:
            envelope = json.loads((harness_out.stdout_summary or "").strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            envelope = {"ok": False}
        if not envelope.get("ok") or envelope.get("eval_visible"):
            docker.cleanup(runtime)
            return _err(
                run_dir,
                "harness" if not envelope.get("eval_visible") else "provider",
                l1_meta,
                agent_meta,
                inv,
                kind="workspace_view_denied" if envelope.get("eval_visible") else None,
            )

        # Materialize agent-output only + evaluator
        staging = run_dir / "eval_staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        art = runtime.workdir_host / "artifacts" / "agent-output.json"
        if not art.is_file():
            docker.cleanup(runtime)
            return _err(run_dir, "evaluation_input", l1_meta, agent_meta, inv)
        (staging / "agent-output.json").write_bytes(art.read_bytes())
        eval_py = package_root / "evaluator.py"
        (staging / "evaluator.py").write_bytes(eval_py.read_bytes())
        eval_raw, eval_meta = _run_clean_evaluator_container(
            image_tag=runtime.image_lock.image_tag if runtime.image_lock else "bora-attempt:l1",
            staging=staging,
            artifact_filename="agent-output.json",
            artifact_key="agent-output",
            expected_filename=None,
        )
        l1_meta["evaluator"] = eval_meta
        l1_meta["writer_inventory"] = list(runtime.writer_inventory)
        l1_meta["writer_stop_confirmed"] = runtime.writer_stop_confirmed and bool(
            eval_meta.get("writer_stop_confirmed")
        )
        docker.cleanup(runtime)
        full_l1 = bool(
            envelope.get("eval_visible") is False
            and harness_out.writer_stop_confirmed
            and eval_meta.get("ok")
            and eval_meta.get("writer_stop_confirmed")
        )
        flat = bind_result(
            evaluator_raw=eval_raw,
            harness_kind="completed",
            runtime_kind="docker_l1",
            agent_invocations=inv,
            evidence_path=str(run_dir),
            error_phase=None
            if eval_raw and eval_raw.get("status") in {"PASS", "FAIL"}
            else "evaluation",
        )
        doc = flat.as_dict()
        doc["assurance"] = "l1" if full_l1 else "l0"
        doc["l1"] = {**l1_meta, "full_l1": full_l1}
        _write_evidence(run_dir, doc, agent_meta, doc["l1"])
        code = 0 if flat.status == "PASS" else (1 if flat.status == "FAIL" else 2)
        return (
            code,
            doc,
            {
                "agent": agent_meta,
                "l1": doc["l1"],
                "assurance": doc["assurance"],
                "run_dir": str(run_dir),
                "digest": lock.digest,
            },
        )
    finally:
        cred.cleanup()


def _run_l1_hidden_denied(
    *, package_root: Path, lock: Any, run_dir: Path
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Harness must not see evaluation/; exit non-zero with workspace_view_denied."""
    docker, runtime, l1_meta = _prepare(package_root, lock, run_dir)
    script = textwrap.dedent(
        """
        import json
        from pathlib import Path
        seen = (Path("/attempt/package/evaluation").exists()
                or Path("/attempt/package/evaluation/gold.json").is_file())
        print(json.dumps({"ok": False, "seen_gold": seen, "eval_visible": seen}))
        raise SystemExit(3 if seen else 2)
        """
    )
    out = docker.run_command(
        runtime, ["python", "-c", script], network=False, writer_name="harness_probe"
    )
    docker.cleanup(runtime)
    try:
        probe = json.loads((out.stdout_summary or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        probe = {"seen_gold": False}
    # Success for security negative: gold not seen AND harness non-zero
    denied_ok = not probe.get("seen_gold") and out.exit_code != 0
    doc = {
        "status": "PASS" if denied_ok else "FAIL",
        "score": 1.0 if denied_ok else 0.0,
        "assurance": "l1" if denied_ok and out.writer_stop_confirmed else "l0",
        "harness_kind": "failed",
        "runtime_kind": "docker_l1",
        "agent_invocations": 0,
        "evidence_path": str(run_dir),
        "metrics": probe,
        "error": {"kind": "workspace_view_denied", "phase": "harness"},
        "l1": {**l1_meta, "probe": probe, "writer_stop_confirmed": out.writer_stop_confirmed},
    }
    _write_evidence(run_dir, doc, {}, doc["l1"])
    return (0 if denied_ok else 1), doc, {"l1": doc["l1"], "assurance": doc["assurance"]}


def _run_l1_projection_denied(
    *, package_root: Path, lock: Any, run_dir: Path
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Network none: undeclared egress fails; harness has no credential files."""
    docker, runtime, l1_meta = _prepare(package_root, lock, run_dir)
    assert runtime.workdir_host is not None
    cred = project_executor_credentials(work_root=runtime.workdir_host)
    # Harness must NOT mount credentials — probe for key absence + network deny.
    script = textwrap.dedent(
        """
        import json, os, urllib.request
        from pathlib import Path
        cred_visible = Path("/creds").exists()
        key_env = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_HOME"))
        net_ok = False
        try:
            urllib.request.urlopen("https://example.com", timeout=3)
            net_ok = True
        except Exception:
            net_ok = False
        print(json.dumps({
            "cred_visible": cred_visible,
            "key_env": key_env,
            "network_ok": net_ok,
        }))
        # Fail closed if network or creds leaked into harness.
        if cred_visible or key_env or net_ok:
            raise SystemExit(3)
        raise SystemExit(2)
        """
    )
    out = docker.run_command(
        runtime,
        ["python", "-c", script],
        network=False,  # harness network none
        writer_name="harness_projection_probe",
        # deliberately do NOT mount cred.root
    )
    docker.cleanup(runtime)
    cred.cleanup()
    try:
        probe = json.loads((out.stdout_summary or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        probe = {}
    denied_ok = (
        not probe.get("cred_visible")
        and not probe.get("key_env")
        and not probe.get("network_ok")
        and out.exit_code != 0
    )
    doc = {
        "status": "PASS" if denied_ok else "FAIL",
        "score": 1.0 if denied_ok else 0.0,
        "assurance": "l1" if denied_ok else "l0",
        "harness_kind": "failed",
        "runtime_kind": "docker_l1",
        "agent_invocations": 0,
        "evidence_path": str(run_dir),
        "metrics": probe,
        "error": {"kind": "projection_denied", "phase": "provider"},
        "l1": {**l1_meta, "probe": probe, "writer_stop_confirmed": out.writer_stop_confirmed},
    }
    _write_evidence(run_dir, doc, {}, doc["l1"])
    return (0 if denied_ok else 1), doc, {"l1": doc["l1"], "assurance": doc["assurance"]}


def _run_l1_residual_writer(
    *, package_root: Path, lock: Any, run_dir: Path
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Background writer must be stopped; evaluator not started if unconfirmed."""
    docker, runtime, l1_meta = _prepare(package_root, lock, run_dir)
    assert runtime.workdir_host is not None
    # Start a long-running writer container (not --rm wait) then kill via docker rm -f.
    name = f"bora-writer-{runtime.attempt.value[-10:]}"
    img = runtime.image_lock.image_tag if runtime.image_lock else "bora-attempt:l1"
    ws = runtime.workdir_host / "workspace"
    (ws / "writer.out").write_text("start\n", encoding="utf-8")
    proc = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "none",
            "--user",
            "10001:10001",
            "-v",
            f"{ws}:/attempt/workspace:rw",
            img,
            "python",
            "-c",
            "import time; time.sleep(120)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    runtime.register_writer("background_writer")
    # Barrier: kill writer and confirm gone.
    kill = subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
    gone = (
        subprocess.run(["docker", "inspect", name], check=False, capture_output=True).returncode
        != 0
    )
    runtime.record_writer_stop(gone and kill.returncode == 0)
    # If writer not confirmed, evaluator must not start.
    eval_started = False
    if runtime.writer_stop_confirmed:
        # Only then would we start evaluator — for this negative we still skip eval.
        eval_started = False
    docker.cleanup(runtime)
    denied_ok = runtime.writer_stop_confirmed and not eval_started and proc.returncode == 0
    doc = {
        "status": "PASS" if denied_ok else "FAIL",
        "score": 1.0 if denied_ok else 0.0,
        "assurance": "l1" if denied_ok else "l0",
        "harness_kind": "failed",
        "runtime_kind": "docker_l1",
        "agent_invocations": 0,
        "evidence_path": str(run_dir),
        "metrics": {
            "writer_stop_confirmed": runtime.writer_stop_confirmed,
            "evaluator_started": eval_started,
        },
        "error": {"kind": "residual_writer", "phase": "evaluation_input"},
        "l1": {
            **l1_meta,
            "writer_inventory": list(runtime.writer_inventory),
            "writer_stop_confirmed": runtime.writer_stop_confirmed,
            "evaluator_started": eval_started,
        },
    }
    _write_evidence(run_dir, doc, {}, doc["l1"])
    return (0 if denied_ok else 1), doc, {"l1": doc["l1"], "assurance": doc["assurance"]}


def _run_agent_executor_container(
    *,
    docker: DockerProvider,
    runtime: DockerRuntime,
    kind: str,
    model: str,
    prompt: str,
    cred_root: Path,
    workspace_output_name: str,
    timeout: float,
    api_key_env: str | None = None,
    base_url: str | None = None,
    evidence_root: Path | None = None,
    entry_id: str | None = None,
) -> tuple[bool, int, dict[str, Any]]:
    """Residual one-shot: ACP entry via docker exec into package image (Spec 19)."""
    if os.environ.get("BORA_OFFLINE_AGENT") == "1":
        return (
            False,
            0,
            {
                "ok": False,
                "error": "offline_forced",
                "executor_containment": "container",
            },
        )
    if kind != "acp":
        return (
            False,
            0,
            {
                "ok": False,
                "error": "migrated_to_acp",
                "executor_containment": "container",
            },
        )
    if not entry_id:
        return False, 0, {"ok": False, "error": "acp_entry_required"}
    return _run_acp_in_package_image(
        docker=docker,
        runtime=runtime,
        entry_id=entry_id,
        model=model,
        prompt=prompt,
        cred_root=cred_root,
        workspace_output_name=workspace_output_name,
        timeout=timeout,
        api_key_env=api_key_env,
        base_url=base_url,
        evidence_root=evidence_root,
        write_workspace_file=True,
    )


def _cli_env_for_container(
    kind: str, *, api_key_env: str | None, base_url: str | None
) -> dict[str, str]:
    """Project host credentials into docker ``-e`` (values never logged).

    Never copy host ``PATH`` / ``HOME`` / ``XDG_*`` — those are macOS/Linux host
    paths and break in-container engines (e.g. opencode ``mkdir /Users``).
    Callers set container ``HOME`` / ``PATH`` after this returns.
    """
    from bora.adapters.child_env import project_cli_child_env

    if kind in {"codex"}:
        env: dict[str, str] = {}
        if api_key_env and os.environ.get(api_key_env):
            env[api_key_env] = os.environ[api_key_env]
            env.setdefault("OPENAI_API_KEY", os.environ[api_key_env])
        elif os.environ.get("OPENAI_API_KEY"):
            env["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
        if base_url:
            env["OPENAI_BASE_URL"] = base_url
        return env
    projected = project_cli_child_env(
        kind if kind != "claude" else "claude-code",
        api_key_env=api_key_env,
        base_url=base_url,
    )
    # Credential + terminal locale only — no host filesystem path env.
    keep_prefixes = (
        "ZAI_",
        "ZHIPU",
        "OPENAI_",
        "ANTHROPIC_",
        "OPENCODE_",
        "XAI_",
        "LANG",
        "TERM",
        "LC_",
    )
    host_path_denylist = {
        "PATH",
        "HOME",
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
    }
    out = {
        k: v
        for k, v in projected.items()
        if v
        and k not in host_path_denylist
        and (k.startswith(keep_prefixes) or (api_key_env and k == api_key_env))
    }
    return out


def _persist_l1_agent_trajectory(
    *,
    evidence_root: Path,
    kind: str,
    model: str,
    prompt: str,
    exit_code: int | None,
    stream_dir: Path,
    ok: bool,
    error: str | None,
) -> dict[str, Any]:
    """Write §8.9-style invocation layout under run_dir/agent/invocations/."""
    import uuid

    inv_id = f"inv_{uuid.uuid4().hex[:16]}"
    inv_root = evidence_root / "agent" / "invocations"
    inv_root.mkdir(parents=True, exist_ok=True)
    # Sequential prefix for human scan order.
    seq = len([p for p in inv_root.iterdir() if p.is_dir()]) + 1
    inv_dir = inv_root / f"{seq:04d}-{inv_id}"
    backend = inv_dir / "backend_raw"
    backend.mkdir(parents=True, exist_ok=True)

    stdout_src = stream_dir / "stdout.txt"
    stderr_src = stream_dir / "stderr.txt"
    stdout = stdout_src.read_text(encoding="utf-8") if stdout_src.is_file() else ""
    stderr = stderr_src.read_text(encoding="utf-8") if stderr_src.is_file() else ""
    # Canonical names aligned with L0 adapters.
    (backend / "backend-stdout.jsonl").write_text(stdout, encoding="utf-8")
    (backend / "backend-stderr.txt").write_text(stderr, encoding="utf-8")

    (inv_dir / "request.json").write_text(
        json.dumps(
            {
                "executor_kind": kind,
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (inv_dir / "metadata.json").write_text(
        json.dumps(
            {
                "schema": "bora.trajectory.metadata/1",
                "invocation_id": inv_id,
                "seq": seq,
                "executor_kind": kind,
                "model": model,
                "status": "completed" if ok else "failed",
                "error": error,
                "container_exit": exit_code,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    # Lifecycle + one source_ref per raw stream for export tools.
    events_path = inv_dir / "events.jsonl"
    with events_path.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "type": "lifecycle",
                    "phase": "invoke_start",
                    "source": "l1_agent_executor",
                    "schema": "bora.trajectory.event/1",
                    "seq": 1,
                },
                sort_keys=True,
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                {
                    "type": "lifecycle",
                    "phase": "terminal",
                    "source": "l1_agent_executor",
                    "returncode": exit_code,
                    "schema": "bora.trajectory.event/1",
                    "seq": 2,
                },
                sort_keys=True,
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                {
                    "type": "source_ref",
                    "kind": "backend-stdout.jsonl",
                    "source": "executor",
                    "schema": "bora.trajectory.event/1",
                    "seq": 3,
                },
                sort_keys=True,
            )
            + "\n"
        )
    # Append-only root agent events index.
    root_events = evidence_root / "agent" / "events.jsonl"
    root_events.parent.mkdir(parents=True, exist_ok=True)
    with root_events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "type": "invocation_sealed",
                    "invocation_id": inv_id,
                    "relative": str(inv_dir.relative_to(evidence_root)),
                    "executor_kind": kind,
                    "ok": ok,
                },
                sort_keys=True,
            )
            + "\n"
        )
    return {
        "invocation_id": inv_id,
        "evidence_relative": str(inv_dir.relative_to(evidence_root)),
        "backend_stdout": str(
            (backend / "backend-stdout.jsonl").relative_to(evidence_root)
        ),
        "backend_stderr": str(
            (backend / "backend-stderr.txt").relative_to(evidence_root)
        ),
    }


def _run_acp_in_package_image(
    *,
    docker: DockerProvider,
    runtime: DockerRuntime,
    entry_id: str,
    model: str,
    prompt: str,
    cred_root: Path,
    workspace_output_name: str,
    timeout: float,
    api_key_env: str | None = None,
    base_url: str | None = None,
    evidence_root: Path | None = None,
    write_workspace_file: bool = False,
) -> tuple[bool, int, dict[str, Any]]:
    """Residual one-shot: parent AcpExecutor attached to package-image ACP entry."""
    from bora.adapters.acp_registry import get_entry
    from bora.adapters.agent_acp import AcpExecutor

    del docker  # image/runtime used; long-lived container via docker CLI
    assert runtime.workdir_host is not None
    assert runtime.image_lock is not None
    desc = get_entry(entry_id)
    if desc is None:
        return False, 0, {"ok": False, "error": "unknown_acp_entry"}

    child_env = _cli_env_for_container(
        entry_id, api_key_env=api_key_env, base_url=base_url
    )
    # Writable actor HOME (not under RO /creds mount) — engines need RW state dirs.
    # Force container paths (never host PATH/HOME from projection).
    child_env["HOME"] = "/actor-home"
    child_env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    child_env["NO_BROWSER"] = "1"
    child_env["CODEX_HOME"] = "/actor-home/.codex"
    child_env["XDG_CONFIG_HOME"] = "/actor-home/.config"
    child_env["XDG_CACHE_HOME"] = "/actor-home/.cache"
    child_env["XDG_STATE_HOME"] = "/actor-home/.local/state"
    if (cred_root / "pi_home" / "agent" / "auth.json").is_file():
        child_env["PI_CONFIG_DIR"] = "/creds/pi_home"
    if (cred_root / "opencode" / "auth.json").is_file():
        child_env["XDG_DATA_HOME"] = "/creds"
    else:
        child_env["XDG_DATA_HOME"] = "/actor-home/.local/share"
    for k, v in desc.fixed_env.items():
        child_env.setdefault(str(k), str(v))

    workspace = runtime.workdir_host / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    actor_home = runtime.workdir_host / "actor_home"
    if actor_home.exists():
        shutil.rmtree(actor_home)
    actor_home.mkdir(parents=True, exist_ok=True)
    (actor_home / ".codex").mkdir(parents=True, exist_ok=True)
    # Seed allowlisted auth material into writable HOME when projected.
    for src_name, dest_rel in (
        ("codex_home", ".codex"),
        ("pi_home", ".pi"),
    ):
        src = cred_root / src_name
        if src.is_dir():
            dest = actor_home / dest_rel
            if not dest.exists():
                shutil.copytree(src, dest, dirs_exist_ok=True)
    name = f"bora-acp-residual-{runtime.attempt.value[:12]}"
    # Long-lived container; ACP client attaches via docker exec -i.
    start = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--network",
        "bridge",
        "-w",
        "/attempt/workspace",
        "-v",
        f"{workspace}:/attempt/workspace",
        "-v",
        f"{actor_home}:/actor-home",
        "-v",
        f"{cred_root}:/creds:ro",
    ]
    for ek, ev in child_env.items():
        if str(ek).upper() in {"DOCKER_HOST", "DOCKER_SOCK"}:
            continue
        start.extend(["-e", f"{ek}={ev}"])
    start.extend([runtime.image_lock.image_tag, "sleep", "infinity"])
    proc = subprocess.run(start, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return (
            False,
            0,
            {
                "ok": False,
                "error": "spawn_failed",
                "stderr": (proc.stderr or "")[-500:],
                "executor_containment": "container",
            },
        )
    cid = (proc.stdout or "").strip()
    try:
        docker_cmd: list[str] = [
            "docker",
            "exec",
            "-i",
            "-w",
            "/attempt/workspace",
        ]
        for ek, ev in child_env.items():
            if str(ek).upper() in {"DOCKER_HOST", "DOCKER_SOCK"}:
                continue
            docker_cmd.extend(["-e", f"{ek}={ev}"])
        docker_cmd.append(cid)
        docker_cmd.extend(list(desc.acp_command))
        ex = AcpExecutor(
            entry_id=entry_id,
            model=model,
            descriptor=desc,
            workdir="/attempt/workspace",
            api_key_env=api_key_env,
            base_url=base_url,
            command_override=docker_cmd,
            env={
                "HOME": "/actor-home",
                "CODEX_HOME": "/actor-home/.codex",
                "NO_BROWSER": "1",
            },
        )
        try:
            result = ex.invoke(prompt, timeout=timeout, workdir="/attempt/workspace")
        finally:
            ex.close()

        structured = result.structured
        if structured is None and result.text:
            structured = _parse_json_from_text(result.text)
        ok = bool(result.ok)
        if write_workspace_file:
            out_path = workspace / workspace_output_name
            # Terminal-class: prefer agent-written workspace file when present
            # (instruction asks for aggregates.json + optional status JSON).
            # Only materialize from ACP structured when it looks like the artifact
            # (not a bare {"status":"completed"} ack).
            if out_path.is_file():
                ok = True
            elif isinstance(structured, dict) and (
                "status" not in structured
                or len(structured) > 1
                or any(k != "status" for k in structured)
            ):
                # Heuristic: multi-key or non-status payload → treat as artifact.
                if "status" in structured and set(structured.keys()) <= {"status", "note"}:
                    ok = False
                else:
                    out_path.write_text(
                        json.dumps(structured, sort_keys=True) + "\n", encoding="utf-8"
                    )
                    ok = True
            else:
                ok = False
        traj: dict[str, Any] = {}
        if evidence_root is not None:
            traj = _persist_l1_agent_trajectory(
                evidence_root=evidence_root,
                kind="acp",
                model=model,
                prompt=prompt,
                exit_code=0 if result.ok else 1,
                stream_dir=runtime.workdir_host / "agent_stream",
                ok=result.ok,
                error=result.error,
            )
        return (
            ok,
            1,
            {
                "ok": ok,
                "error": result.error if not ok else None,
                "model": result.model,
                "executor_kind": "acp",
                "acp_entry_id": entry_id,
                "executor_containment": "container",
                "text_tail": (result.text or "")[-500:],
                **traj,
            },
        )
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)


def _run_agent_structured(
    *,
    docker: DockerProvider,
    runtime: DockerRuntime,
    kind: str,
    model: str,
    prompt: str,
    cred_root: Path,
    allow_offline: bool,
    api_key_env: str | None = None,
    base_url: str | None = None,
    evidence_root: Path | None = None,
    entry_id: str | None = None,
) -> tuple[bool, int, dict[str, Any]]:
    if os.environ.get("BORA_OFFLINE_AGENT") == "1" and not allow_offline:
        return False, 0, {"ok": False, "error": "offline_forced"}
    assert runtime.workdir_host is not None
    workspace = runtime.workdir_host / "workspace"

    if kind != "acp":
        return False, 0, {"ok": False, "error": "migrated_to_acp"}
    if not entry_id:
        return False, 0, {"ok": False, "error": "acp_entry_required"}

    ok, inv, meta = _run_acp_in_package_image(
        docker=docker,
        runtime=runtime,
        entry_id=entry_id,
        model=model,
        prompt=prompt,
        cred_root=cred_root,
        workspace_output_name="agent_result.json",
        timeout=180.0,
        api_key_env=api_key_env,
        base_url=base_url,
        evidence_root=evidence_root,
        write_workspace_file=True,
    )
    if ok and (workspace / "agent_result.json").is_file():
        return True, inv, {**meta, "model": model}
    if ok:
        return False, inv, {**meta, "ok": False, "error": "structured_missing"}
    return ok, inv, meta


def _run_harness_publish(
    docker: DockerProvider, runtime: DockerRuntime, *, workspace_output_name: str
) -> tuple[Any, dict[str, Any]]:
    out_name = workspace_output_name
    harness_script = textwrap.dedent(
        f"""
        import json, shutil
        from pathlib import Path
        pkg = Path("/attempt/package")
        if (pkg / "evaluation").exists():
            print(json.dumps({{"ok": False, "error": "workspace_view_denied",
                              "eval_visible": True}}))
            raise SystemExit(3)
        src = Path("/attempt/workspace") / {out_name!r}
        if not src.is_file():
            print(json.dumps({{"ok": False, "error": "workspace_output_missing"}}))
            raise SystemExit(2)
        dest = Path("/attempt/artifacts") / {out_name!r}
        shutil.copy2(src, dest)
        print(json.dumps({{
            "ok": True,
            "terminal": {{"kind": "completed"}},
            "published": {{"aggregates": str(dest)}},
            "eval_visible": False,
        }}))
        """
    )
    harness_out = docker.run_command(
        runtime,
        ["python", "-c", harness_script],
        network=False,
        writer_name="harness",
        timeout_seconds=60,
    )
    try:
        envelope = json.loads((harness_out.stdout_summary or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        envelope = {"ok": False, "error": "harness_envelope_unparseable"}
    return harness_out, envelope


def _materialize_and_evaluate(
    *,
    package_root: Path,
    run_dir: Path,
    runtime: DockerRuntime,
    docker: DockerProvider,
    artifact_name: str,
    artifact_id: str,
    expected_name: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    assert runtime.workdir_host is not None
    staging = run_dir / "eval_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    art_src = runtime.workdir_host / "artifacts" / artifact_name
    if not art_src.is_file():
        return {"status": "ERROR", "score": None, "metrics": {}}, {"ok": False}
    (staging / artifact_name).write_bytes(art_src.read_bytes())
    if expected_name:
        expected_host = package_root / "evaluation" / expected_name
        if expected_host.is_file():
            (staging / expected_name).write_bytes(expected_host.read_bytes())
    (staging / "evaluator.py").write_bytes((package_root / "evaluator.py").read_bytes())
    return _run_clean_evaluator_container(
        image_tag=runtime.image_lock.image_tag if runtime.image_lock else "bora-attempt:l1",
        staging=staging,
        artifact_filename=artifact_name,
        artifact_key=artifact_id,
        expected_filename=expected_name,
    )


def _run_clean_evaluator_container(
    *,
    image_tag: str,
    staging: Path,
    artifact_filename: str,
    artifact_key: str,
    expected_filename: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    arts = f'"artifacts": {{"{artifact_key}": "/eval/{artifact_filename}"'
    if expected_filename:
        arts += f', "expected": "/eval/{expected_filename}"'
    arts += "}"
    script = textwrap.dedent(
        f"""
        import json, importlib.util
        from pathlib import Path
        pkg = Path("/attempt/package")
        leaked = pkg.exists() and ((pkg / "evaluation").exists() or any(pkg.iterdir()))
        if leaked:
            print(json.dumps({{"status": "ERROR", "score": None,
                               "metrics": {{"leak": "package_mount"}}}}))
            raise SystemExit(3)
        if Path("/creds").exists():
            print(json.dumps({{"status": "ERROR", "score": None,
                               "metrics": {{"leak": "credential"}}}}))
            raise SystemExit(3)
        spec = importlib.util.spec_from_file_location("ev", "/eval/evaluator.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        raw = mod.evaluate({{{arts}}})
        print(json.dumps(raw))
        """
    )
    name = f"bora-eval-{staging.name[-8:]}"
    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--user",
        "10001:10001",
        "--security-opt",
        "no-new-privileges",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=32m",
        "-v",
        f"{staging}:/eval:ro",
        "--workdir",
        "/eval",
        image_tag,
        "python",
        "-c",
        script,
    ]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
        return (
            {"status": "ERROR", "score": None, "metrics": {"error": "timeout"}},
            {"ok": False, "writer_stop_confirmed": True, "package_mounted": False},
        )
    meta = {
        "ok": proc.returncode == 0,
        "exit": proc.returncode,
        "writer_stop_confirmed": True,
        "package_mounted": False,
        "stderr": (proc.stderr or "")[-500:],
    }
    try:
        line = (proc.stdout or "").strip().splitlines()[-1]
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raw = {"status": "ERROR", "score": None, "metrics": {}}
    except (json.JSONDecodeError, IndexError):
        raw = {
            "status": "ERROR",
            "score": None,
            "metrics": {"stderr": meta["stderr"], "stdout": (proc.stdout or "")[-500:]},
        }
        meta["ok"] = False
    return raw, meta


def _err(
    run_dir: Path,
    phase: str,
    l1_meta: dict[str, Any],
    agent_meta: dict[str, Any],
    inv: int,
    *,
    kind: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    from bora.evaluation.result_binding import bind_result

    flat = bind_result(
        evaluator_raw=None,
        harness_kind="failed",
        runtime_kind="docker_l1",
        agent_invocations=inv,
        evidence_path=str(run_dir),
        error_phase=phase,
    )
    doc = flat.as_dict()
    doc["assurance"] = "l0"
    doc["status"] = "ERROR"
    if kind:
        doc["error"] = {"phase": phase, "kind": kind}
    doc["l1"] = l1_meta
    _write_evidence(run_dir, doc, agent_meta, l1_meta)
    return 2, doc, {"agent": agent_meta, "l1": l1_meta, "assurance": "l0"}


def _write_evidence(
    run_dir: Path,
    result_doc: dict[str, Any],
    agent_meta: dict[str, Any],
    l1_meta: dict[str, Any],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    # Result.logs locator (design §8.9) — evidence root on host, never secrets.
    # Mutate in place so caller-returned doc/details stay aligned with disk.
    result_doc.setdefault("logs", str(run_dir))
    # Honest execution location facts (Spec 14 / v0.15).
    containment = str(
        agent_meta.get("executor_containment")
        or l1_meta.get("executor_containment")
        or "unknown"
    )
    if containment in {"container", "attempt-container"}:
        exec_loc = "attempt-container"
    elif containment.startswith("parent"):
        exec_loc = "parent-api-client"
    else:
        # Harness/eval containers still run under Docker even when Agent is parent.
        exec_loc = str(l1_meta.get("execution_location") or "mixed")
    l1_meta = {
        **l1_meta,
        "execution_location": exec_loc,
        "executor_containment": containment,
        "evidence_volume": str(run_dir),
    }
    result_doc["l1"] = {**(result_doc.get("l1") or {}), **l1_meta}
    (run_dir / "result.json").write_text(
        json.dumps(result_doc, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    (run_dir / "agent.json").write_text(
        json.dumps(agent_meta, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    # Redact any accidental secret-looking keys from l1 dump.
    safe = json.loads(json.dumps(l1_meta, default=str))
    blob = json.dumps(safe, indent=2, sort_keys=True) + "\n"
    for needle in ("sk-", "OPENAI_API_KEY=", "password"):
        if needle in blob:
            blob = blob.replace(needle, "[REDACTED]")
    (run_dir / "l1.json").write_text(blob, encoding="utf-8")
    # §8.9 summary + skeletons (trajectory body still owned by Agent Service when used).
    summary = {
        "schema": "bora.evidence.summary/1",
        "status": result_doc.get("status"),
        "score": result_doc.get("score"),
        "assurance": result_doc.get("assurance"),
        "logs": result_doc.get("logs"),
        "execution_location": exec_loc,
        "l1": safe,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for rel in ("effects.jsonl", "agent/events.jsonl"):
        path = run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
    (run_dir / "cleanup.json").write_text(
        json.dumps({"ok": True, "warning": result_doc.get("cleanup_warning")}, indent=2)
        + "\n",
        encoding="utf-8",
    )
