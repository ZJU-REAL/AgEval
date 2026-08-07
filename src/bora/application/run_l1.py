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

    return _err(
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

    docker, runtime, l1_meta = _prepare(package_root, lock, run_dir, network_mode=network_mode)
    assert runtime.workdir_host is not None
    assert runtime.attempt is not None

    # Seed Attempt workspace for terminal-class packages (data/ only — no Agent invoke).
    workspace_host = runtime.workdir_host / "workspace"
    workspace_host.mkdir(parents=True, exist_ok=True)
    data_dir = package_root / "data"
    if data_dir.is_dir():
        for src in data_dir.iterdir():
            if src.is_file():
                shutil.copy2(src, workspace_host / src.name)
    # Isolation / offline fixture: copy solution/* into workspace without Runtime invoke.
    if allow_offline_agent or os.environ.get("BORA_L1_USE_SOLUTION") == "1":
        solution_dir = package_root / "solution"
        if solution_dir.is_dir():
            for src in solution_dir.iterdir():
                if src.is_file():
                    shutil.copy2(src, workspace_host / src.name)
            l1_meta["solution_seed"] = True

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
                }
                for p in profiles
            ],
        }
        if lock.provenance is not None:
            lock_doc["provenance"] = _thaw_lock(lock.provenance)
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
                f"migrated_to_acp: L1 executor {kind!r} requires executor: acp + options.entry"
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
            docker_cmd.extend(["sh", "-c", 'umask 002; exec "$@"', "bora-actor", *acp_argv])
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
    # Gold materialize for terminal-class packages (never mounted during harness).
    expected_filename: str | None = None
    expected_host = package_root / "evaluation" / "expected.json"
    if expected_host.is_file():
        (staging / "expected.json").write_bytes(expected_host.read_bytes())
        expected_filename = "expected.json"

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
        agent_meta.get("executor_containment") or l1_meta.get("executor_containment") or "unknown"
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
        json.dumps({"ok": True, "warning": result_doc.get("cleanup_warning")}, indent=2) + "\n",
        encoding="utf-8",
    )
