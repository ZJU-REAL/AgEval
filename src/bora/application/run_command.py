"""Production ``bora run`` use case — Core 1–5 vertical slice (v0.6)."""

from __future__ import annotations

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
) -> tuple[int, FlatResult, dict[str, Any]]:
    """Run one foreground Attempt and return (exit_code, result, details)."""
    package_root = package_root.resolve()
    config = ConfigCore(package_reader=LocalPackageReader())
    try:
        lock = config.load_and_lock(
            package_root,
            task_id,
            capabilities=DeclarationCapabilityCatalog(),
        )
    except ConfigError:
        # unknown task etc. before Attempt/evidence
        raise

    evidence_root = (evidence_root or (package_root / ".bora" / "runs")).resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    # Unique Run identity per invocation — never overwrite prior evidence by lock digest alone.
    from bora.runtime.identity import IdentityFactory

    run_id = IdentityFactory().new_run().value
    run_dir = evidence_root / f"{lock.digest.replace(':', '_')[:48]}_{run_id[:16]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    agent_invocations = 0
    agent_meta: dict[str, Any] = {}
    assurance = "l0"
    l1_meta: dict[str, Any] = {}

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
        agent_service = ParentAgentService(
            profiles=[p for p in profiles if isinstance(p, dict)],
            agent_invocation_limit=inv_limit,
            resolve_executor=lambda kind, model: resolve_executor(kind, model=model),
        )
        # Unix socket path must stay short on macOS (~104 bytes).
        import tempfile

        short = Path(tempfile.gettempdir()) / f"bora-ags-{run_id[:12]}.sock"
        agent_sock_path = short
        agent_server = AgentServiceServer(agent_service, agent_sock_path)
        agent_server.start()
    elif agent_profile is not None:
        from bora.adapters.agent_openai_http import resolve_executor

        model = str(agent_profile.get("model") or "gpt-5.4-mini")
        kind = str(agent_profile.get("executor") or "codex")
        question = str(params.get("question") or 'Return JSON {"answer": 42}')
        try:
            executor = resolve_executor(kind, model=model)
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
        case_class = str(params.get("case_class") or "")
        workspace_root: Path | None = None
        if case_class == "terminal_workspace":
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
            # Longer timeout for file-writing agents.
            invoke_timeout = float(params.get("agent_timeout_seconds") or 180)
            result = executor.invoke(
                question, timeout=invoke_timeout, workdir=str(workspace_root)
            )
            agent_invocations = 1
            agent_meta = {
                "model": result.model,
                "ok": result.ok,
                "error": result.error,
                "executor": kind,
                "case_class": case_class,
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
        # Docker preflight / scaffolding only until harness+evaluator run inside L1.
        # Honest grade remains l0 (or ERROR on preflight failure) — never stamp
        # assurance:l1 while workload still uses host LocalProcessProvider.
        from bora.adapters.provider_docker import DockerProvider, ensure_image_lock
        from bora.runtime.identity import IdentityFactory

        try:
            repo_lock = Path.cwd() / ".bora" / "runtime-images" / "provider-l1.json"
            lock_path = repo_lock if repo_lock.is_file() else ensure_image_lock(Path.cwd())
            docker = DockerProvider(image_lock_path=lock_path)
            factory = IdentityFactory()
            run = factory.new_run()
            trial = factory.new_trial(run, lock.digest)
            attempt = factory.new_attempt(trial)
            work = run_dir / "l1-work"
            runtime = docker.prepare(
                attempt,
                package_root=package_root,
                work_root=work,
                network_mode=str(provider_cfg.get("network") or "none"),
                hide_evaluation=True,
            )
            probe = docker.run_command(
                runtime,
                [
                    "python",
                    "-c",
                    "from pathlib import Path; "
                    "p=Path('/attempt/package/evaluation'); "
                    "print('eval_exists', p.exists())",
                ],
                network=False,
                timeout_seconds=60,
            )
            # Fail closed if filtered mount still exposes evaluation/.
            if "eval_exists True" in (probe.stdout_summary or ""):
                docker.cleanup(runtime)
                raise RuntimeError("workspace_view_denied: evaluation/ visible in package mount")
            l1_meta = {
                "image": (runtime.image_lock.image_digest if runtime.image_lock else ""),
                "platform": (runtime.image_lock.platform if runtime.image_lock else ""),
                "probe_exit": probe.exit_code,
                "probe_stdout": probe.stdout_summary.strip(),
                "writer_stop_confirmed": probe.writer_stop_confirmed,
                "containment": "docker_preflight_only",
                "assurance_note": "workload remains host L0 until containerized harness/evaluator",
            }
            # Honest: preflight scaffolding is not L1 Attempt isolation.
            assurance = "l0"
            docker.cleanup(runtime)
        except Exception as exc:  # noqa: BLE001
            flat = bind_result(
                evaluator_raw=None,
                harness_kind="failed",
                runtime_kind="local_l0",
                agent_invocations=0,
                evidence_path=str(run_dir),
                error_phase="provider",
                cleanup_warning=f"{type(exc).__name__}: {exc}",
            )
            summary = flat.as_dict()
            summary["assurance"] = "l0"
            summary["status"] = "ERROR"
            summary["error"] = {
                "phase": "provider",
                "kind": getattr(exc, "error_code", "provider_l1_unavailable"),
                "message": str(exc),
            }
            (run_dir / "result.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return 2, flat, {"l1": {"error": str(exc), "containment": "docker_preflight_only"}}

    try:
        harness_out = await run_harness_package(
            lock,
            package_root,
            timeout_seconds=float(params.get("harness_timeout_seconds") or 180.0)
            if isinstance(params, dict)
            else 180.0,
            agent_service_sock=str(agent_sock_path) if agent_sock_path else None,
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

    flat = bind_result(
        evaluator_raw=evaluator_raw,
        harness_kind=harness_kind,
        # docker kind preflight does not upgrade isolation grade until full L1 workload.
        runtime_kind="local_l0",
        agent_invocations=agent_invocations,
        evidence_path=str(
            run_dir.relative_to(package_root) if run_dir.is_relative_to(package_root) else run_dir
        ),
        error_phase=error_phase,
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
    }
    if l1_meta:
        details["l1"] = l1_meta
    return code, flat, details


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
