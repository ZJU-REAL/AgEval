"""Full L1 Attempt path: containerized harness + clean evaluator runtime.

Agent Executor may still run on the parent with *workspace-only* cwd (no package
gold mount). Harness and Evaluator always run in separate Docker containers with
filtered/physical views. ``assurance: l1`` only after writer-stop + clean eval.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from bora.adapters.provider_docker import DockerProvider, ensure_image_lock
from bora.runtime.identity import IdentityFactory


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
    """Execute terminal-class L1 journey and return (exit_code, result_doc, details)."""
    from bora.evaluation.result_binding import bind_result

    package_root = package_root.resolve()
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, lock.digest)
    attempt = factory.new_attempt(trial)

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
        network_mode="none",
        hide_evaluation=True,
    )
    assert runtime.workdir_host is not None
    workspace = runtime.workdir_host / "workspace"
    artifacts = runtime.workdir_host / "artifacts"

    # Seed workspace from package data/ (no evaluation/ gold).
    data_dir = package_root / "data"
    if data_dir.is_dir():
        for src in data_dir.iterdir():
            if src.is_file():
                shutil.copy2(src, workspace / src.name)

    l1_meta: dict[str, Any] = {
        "containment": "full_l1_attempt",
        "image": runtime.image_lock.image_digest if runtime.image_lock else "",
        "platform": runtime.image_lock.platform if runtime.image_lock else "",
        "attempt_id": attempt.value,
    }

    # --- Agent Executor (parent boundary): cwd = workspace only ---
    from bora.adapters.agent_openai_http import resolve_executor
    from bora.config.model import thaw

    profiles = thaw(lock.agent_profiles)
    params = thaw(lock.parameters)
    profile = next((p for p in profiles if isinstance(p, dict)), None)
    if profile is None:
        docker.cleanup(runtime)
        flat = bind_result(
            evaluator_raw=None,
            harness_kind="failed",
            runtime_kind="docker_l1",
            agent_invocations=0,
            evidence_path=str(run_dir),
            error_phase="config",
        )
        return 2, {**flat.as_dict(), "assurance": "l0", "l1": l1_meta}, {"error": "no_profile"}

    model = str(profile.get("model") or "gpt-5.4-mini")
    kind = str(profile.get("executor") or "codex")
    instruction = (workspace / "instruction.md").read_text(encoding="utf-8")
    solution_seed = package_root / "solution" / workspace_output_name
    if (workspace / workspace_output_name).is_file():
        agent_ok = True
        agent_error = None
        agent_meta = {
            **agent_meta,
            "ok": True,
            "workdir": str(workspace),
            "workspace_output": workspace_output_name,
            "source": "preexisting_workspace",
        }
    elif solution_seed.is_file() and (
        allow_offline_agent or __import__("os").environ.get("BORA_L1_USE_SOLUTION") == "1"
    ):
        # Deterministic isolation gate / offline path: solution seed is not gold
        # (evaluation/expected remains evaluator-only after barrier).
        shutil.copy2(solution_seed, workspace / workspace_output_name)
        agent_ok = True
        agent_error = None
        agent_invocations = 0
        agent_meta = {
            **agent_meta,
            "ok": True,
            "workdir": str(workspace),
            "workspace_output": workspace_output_name,
            "source": "solution_seed",
        }
    else:
        try:
            executor = resolve_executor(kind, model=model)
        except KeyError:
            docker.cleanup(runtime)
            flat = bind_result(
                evaluator_raw=None,
                harness_kind="failed",
                runtime_kind="docker_l1",
                agent_invocations=0,
                evidence_path=str(run_dir),
                error_phase="config",
            )
            return 2, {**flat.as_dict(), "assurance": "l0"}, {"error": "executor_unknown"}
        timeout = float(params.get("agent_timeout_seconds") or 300)
        result = executor.invoke(instruction, timeout=timeout, workdir=str(workspace))
        agent_invocations = 1
        agent_ok = bool(result.ok and (workspace / workspace_output_name).is_file())
        agent_error = result.error
        agent_meta = {
            **agent_meta,
            "model": result.model,
            "ok": result.ok,
            "error": result.error,
            "executor": kind,
            "workdir": str(workspace),
            "workspace_output": workspace_output_name,
            "source": "executor",
        }
        if not agent_ok and not allow_offline_agent:
            docker.cleanup(runtime)
            flat = bind_result(
                evaluator_raw=None,
                harness_kind="failed",
                runtime_kind="docker_l1",
                agent_invocations=agent_invocations,
                evidence_path=str(run_dir),
                error_phase="agent",
            )
            doc = flat.as_dict()
            doc["assurance"] = "l0"
            doc["status"] = "ERROR"
            doc["l1"] = {**l1_meta, "phase": "agent", "error": agent_error}
            _write_evidence(run_dir, doc, agent_meta, l1_meta)
            return 2, doc, {"agent": agent_meta, "l1": l1_meta, "assurance": "l0"}

    # --- Harness container: filtered package, no evaluation/, publish artifact ---
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
        timeout_seconds=60,
    )
    l1_meta["harness_exit"] = harness_out.exit_code
    l1_meta["harness_writer_stop"] = harness_out.writer_stop_confirmed
    l1_meta["harness_stdout"] = (harness_out.stdout_summary or "")[-2000:]
    harness_ok = harness_out.exit_code == 0 and harness_out.writer_stop_confirmed
    try:
        envelope = json.loads((harness_out.stdout_summary or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        envelope = {"ok": False, "error": "harness_envelope_unparseable"}
    if envelope.get("eval_visible"):
        docker.cleanup(runtime)
        flat = bind_result(
            evaluator_raw=None,
            harness_kind="failed",
            runtime_kind="docker_l1",
            agent_invocations=agent_invocations,
            evidence_path=str(run_dir),
            error_phase="provider",
        )
        doc = flat.as_dict()
        doc["assurance"] = "l0"
        doc["status"] = "ERROR"
        doc["error"] = {"kind": "workspace_view_denied", "message": "evaluation/ visible"}
        doc["l1"] = l1_meta
        _write_evidence(run_dir, doc, agent_meta, l1_meta)
        return 2, doc, {"l1": l1_meta, "assurance": "l0"}

    if not harness_ok or not envelope.get("ok"):
        docker.cleanup(runtime)
        flat = bind_result(
            evaluator_raw=None,
            harness_kind="failed",
            runtime_kind="docker_l1",
            agent_invocations=agent_invocations,
            evidence_path=str(run_dir),
            error_phase="harness",
        )
        doc = flat.as_dict()
        doc["assurance"] = "l0"
        doc["l1"] = l1_meta
        _write_evidence(run_dir, doc, agent_meta, l1_meta)
        return 2, doc, {"harness": envelope, "l1": l1_meta}

    # --- Materialize evaluation inputs after writer barrier ---
    staging = run_dir / "eval_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    art_src = artifacts / workspace_output_name
    if not art_src.is_file():
        docker.cleanup(runtime)
        flat = bind_result(
            evaluator_raw=None,
            harness_kind="completed",
            runtime_kind="docker_l1",
            agent_invocations=agent_invocations,
            evidence_path=str(run_dir),
            error_phase="evaluation_input",
        )
        doc = flat.as_dict()
        doc["assurance"] = "l0"
        _write_evidence(run_dir, doc, agent_meta, l1_meta)
        return 2, doc, {"error": "missing_artifact"}

    staged_agg = staging / workspace_output_name
    staged_agg.write_bytes(art_src.read_bytes())
    expected_host = package_root / "evaluation" / "expected.json"
    staged_expected = staging / "expected.json"
    if expected_host.is_file():
        staged_expected.write_bytes(expected_host.read_bytes())
    eval_py = package_root / "evaluator.py"
    staged_eval = staging / "evaluator.py"
    staged_eval.write_bytes(eval_py.read_bytes())

    # --- Clean evaluator container: only staging mounts, network none ---
    eval_raw, eval_meta = _run_clean_evaluator_container(
        image_tag=runtime.image_lock.image_tag if runtime.image_lock else "bora-attempt:l1",
        staging=staging,
        workspace_output_name=workspace_output_name,
    )
    l1_meta["evaluator"] = eval_meta
    l1_meta["writer_stop_confirmed"] = bool(
        harness_out.writer_stop_confirmed and eval_meta.get("writer_stop_confirmed")
    )

    docker.cleanup(runtime)

    flat = bind_result(
        evaluator_raw=eval_raw,
        harness_kind="completed",
        runtime_kind="docker_l1",
        agent_invocations=agent_invocations,
        evidence_path=str(
            run_dir.relative_to(package_root) if run_dir.is_relative_to(package_root) else run_dir
        ),
        error_phase=None
        if eval_raw and eval_raw.get("status") in {"PASS", "FAIL"}
        else "evaluation",
    )
    doc = flat.as_dict()
    # Full L1 only when harness isolation + clean evaluator + writer stop all hold.
    full_l1 = bool(
        envelope.get("eval_visible") is False
        and harness_out.writer_stop_confirmed
        and eval_meta.get("ok")
        and eval_meta.get("writer_stop_confirmed")
        and not eval_meta.get("package_mounted")
    )
    doc["assurance"] = "l1" if full_l1 else "l0"
    doc["l1"] = {**l1_meta, "full_l1": full_l1}
    if not full_l1:
        # Do not claim PASS with partial isolation stamped as l1.
        pass
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


def _run_clean_evaluator_container(
    *,
    image_tag: str,
    staging: Path,
    workspace_output_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluator-only container: no package mount, network none, staging ro."""
    agg_path = f"/eval/{workspace_output_name}"
    # Image may have empty /attempt/package dir; leak = evaluation/ or files present.
    script = textwrap.dedent(
        """
        import json, importlib.util
        from pathlib import Path
        pkg = Path("/attempt/package")
        leaked = pkg.exists() and (
            (pkg / "evaluation").exists() or any(pkg.iterdir())
        )
        if leaked:
            print(json.dumps({
                "status": "ERROR",
                "score": None,
                "metrics": {"leak": "package_mount"},
            }))
            raise SystemExit(3)
        spec = importlib.util.spec_from_file_location("ev", "/eval/evaluator.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        raw = mod.evaluate({
            "artifacts": {
                "aggregates": "__AGG__",
                "expected": "/eval/expected.json",
            }
        })
        print(json.dumps(raw))
        """
    ).replace("__AGG__", agg_path)
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
        "writer_stop_confirmed": True,  # docker run --rm waited for main process
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


def _write_evidence(
    run_dir: Path,
    result_doc: dict[str, Any],
    agent_meta: dict[str, Any],
    l1_meta: dict[str, Any],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(
        json.dumps(result_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "agent.json").write_text(
        json.dumps(agent_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "l1.json").write_text(
        json.dumps(l1_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
