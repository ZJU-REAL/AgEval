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
from bora.runtime.identity import IdentityFactory


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
    # Structured agent-eval class L1.
    return _run_l1_agent_eval(
        package_root=package_root,
        lock=lock,
        run_dir=run_dir,
        agent_meta=agent_meta,
        allow_offline_agent=allow_offline_agent,
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

    model = str(profile.get("model") or "gpt-5.4-mini")
    kind = str(profile.get("executor") or "codex")
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

    model = str(profile.get("model") or "gpt-5.4-mini")
    kind = str(profile.get("executor") or "codex")
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
) -> tuple[bool, int, dict[str, Any]]:
    """Run agent CLI inside the package Attempt image (no host Homebrew mount)."""
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

    cli_kinds = {"codex", "pi", "opencode", "claude-code", "claude"}
    if kind in cli_kinds:
        return _run_builtin_cli_in_container(
            docker=docker,
            runtime=runtime,
            kind=kind if kind != "claude" else "claude-code",
            model=model,
            prompt=prompt,
            cred_root=cred_root,
            workspace_output_name=workspace_output_name,
            timeout=timeout,
            api_key_env=api_key_env,
            base_url=base_url,
        )

    # HTTP / unknown: parent workspace-only residual (not L1 CLI containment).
    from bora.adapters.agent_registry import resolve_executor

    assert runtime.workdir_host is not None
    workspace = runtime.workdir_host / "workspace"
    try:
        ex = resolve_executor(
            kind, model=model, base_url=base_url, api_key=api_key_env
        )
    except KeyError:
        return False, 0, {"ok": False, "error": "executor_unknown"}
    result = ex.invoke(prompt, timeout=timeout, workdir=str(workspace))
    ok = bool(result.ok and (workspace / workspace_output_name).is_file())
    return (
        ok,
        1,
        {
            "ok": result.ok,
            "error": result.error,
            "model": result.model,
            "executor_containment": "parent_workspace_only",
            "workdir": str(workspace),
        },
    )


def _cli_env_for_container(
    kind: str, *, api_key_env: str | None, base_url: str | None
) -> dict[str, str]:
    """Project host credentials into docker ``-e`` (values never logged)."""
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
    # Drop non-credential noise for docker -e (keep keys that matter).
    keep_prefixes = (
        "ZAI_",
        "ZHIPU",
        "OPENAI_",
        "ANTHROPIC_",
        "OPENCODE_",
        "XAI_",
        "PATH",
        "HOME",
        "LANG",
        "TERM",
    )
    out = {
        k: v
        for k, v in projected.items()
        if v and (k.startswith(keep_prefixes) or (api_key_env and k == api_key_env))
    }
    return out


def _run_builtin_cli_in_container(
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
) -> tuple[bool, int, dict[str, Any]]:
    """Invoke codex/pi/opencode/claude from PATH inside the package image."""
    assert runtime.workdir_host is not None
    workspace = runtime.workdir_host / "workspace"
    binary = {
        "codex": "codex",
        "pi": "pi",
        "opencode": "opencode",
        "claude-code": "claude",
    }.get(kind, kind)

    if kind == "codex":
        cmd = [
            binary,
            "exec",
            "--model",
            model,
            "--ephemeral",
            prompt,
        ]
    elif kind == "pi":
        # model may be provider/model
        cmd = [
            binary,
            "-p",
            "--mode",
            "json",
            "--no-session",
            "--no-tools",
            "--model",
            model,
            prompt,
        ]
    elif kind == "opencode":
        cmd = [
            binary,
            "run",
            "--format",
            "json",
            "--model",
            model,
            "--pure",
            prompt,
        ]
    else:  # claude-code
        cmd = [
            binary,
            "-p",
            "--output-format",
            "json",
            "--model",
            model,
            prompt,
        ]

    child_env = _cli_env_for_container(
        kind, api_key_env=api_key_env, base_url=base_url
    )
    child_env.setdefault("HOME", "/creds_home")
    child_env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    if kind == "codex":
        child_env.setdefault("CODEX_HOME", "/creds/codex_home")

    mounts = [
        (str(cred_root), "/creds", "ro"),
        (str(Path.home()), "/creds_home", "ro"),
    ]
    uid = os.getuid()
    gid = os.getgid()
    out = docker.run_command(
        runtime,
        cmd,
        network=True,
        network_mode="bridge",
        mounts=mounts,
        user=f"{uid}:{gid}",
        writer_name="agent_executor",
        timeout_seconds=timeout + 30,
        read_only_root=False,
        env=child_env,
    )
    # Persist backend raw under evidence is optional; success if exit 0.
    # Workspace output may be produced by harness after agent; agent ok = CLI exit 0
    # or structured path for packages that only need text (agent-eval style).
    ok = out.exit_code == 0
    # If package expects a workspace file from agent, require it when already used.
    expected = workspace / workspace_output_name
    if expected.is_file():
        ok = ok and True
    return (
        ok,
        1,
        {
            "ok": ok,
            "error": None if ok else f"exit_{out.exit_code}",
            "model": model,
            "executor_kind": kind,
            "executor_containment": "container",
            "container_exit": out.exit_code,
            "container_stderr": (out.stderr_summary or "")[-500:],
            "container_stdout": (out.stdout_summary or "")[-8000:],
            "container_stdout_tail": (out.stdout_summary or "")[-500:],
        },
    )


def _run_codex_in_container(
    *,
    docker: DockerProvider,
    runtime: DockerRuntime,
    model: str,
    prompt: str,
    cred_root: Path,
    workspace_output_name: str,
    timeout: float,
) -> tuple[bool, int, dict[str, Any]]:
    """Codex exec inside Docker with bridge network + credential projection."""
    import shutil as sh

    assert runtime.workdir_host is not None
    codex_bin = sh.which("codex")
    if not codex_bin:
        # Fallback parent workspace-only
        from bora.adapters.agent_codex import CodexExecutor

        ex = CodexExecutor(model=model)
        r = ex.invoke(prompt, timeout=timeout, workdir=str(runtime.workdir_host / "workspace"))
        ok = bool(r.ok and (runtime.workdir_host / "workspace" / workspace_output_name).is_file())
        return (
            ok,
            1,
            {
                "ok": r.ok,
                "error": r.error,
                "executor_containment": "parent_fallback_no_codex_bin",
            },
        )

    # Script: run codex, leave workspace files; do not print secrets.
    script = textwrap.dedent(
        f"""
        import os, subprocess, sys
        os.environ["HOME"] = "/creds_home"
        os.environ["CODEX_HOME"] = "/creds/codex_home"
        key = Path_read = None
        from pathlib import Path
        kp = Path("/creds/openai_api_key")
        if kp.is_file() and kp.read_text().strip():
            os.environ["OPENAI_API_KEY"] = kp.read_text().strip()
        cmd = ["codex", "exec", "--model", {model!r}, "--ephemeral", {prompt!r}]
        p = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout={int(timeout)})
        sys.stdout.write(p.stdout or "")
        sys.stderr.write(p.stderr or "")
        raise SystemExit(p.returncode)
        """
    )
    # Fix script - use Path properly
    script = textwrap.dedent(
        f"""
        import os, subprocess, sys
        from pathlib import Path
        os.environ["HOME"] = "/creds_home"
        ch = Path("/creds/codex_home")
        if ch.is_dir():
            os.environ["CODEX_HOME"] = str(ch)
        kp = Path("/creds/openai_api_key")
        if kp.is_file() and kp.read_text(encoding="utf-8").strip():
            os.environ["OPENAI_API_KEY"] = kp.read_text(encoding="utf-8").strip()
        cmd = ["codex", "exec", "--model", {model!r}, "--ephemeral", {prompt!r}]
        p = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout={int(timeout)})
        print(p.stdout or "")
        print(p.stderr or "", file=sys.stderr)
        raise SystemExit(p.returncode)
        """
    )
    uid = os.getuid()
    gid = os.getgid()
    mounts = [
        (str(cred_root), "/creds", "ro"),
        (str(Path.home()), "/creds_home", "ro"),
        (codex_bin, "/usr/local/bin/codex", "ro"),
    ]
    # Also need node/runtime deps for codex - mount may fail. Prefer parent if container fails.
    out = docker.run_command(
        runtime,
        ["python", "-c", script],
        network=True,
        network_mode="bridge",
        mounts=mounts,
        user=f"{uid}:{gid}",
        writer_name="agent_executor",
        timeout_seconds=timeout + 30,
        read_only_root=False,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
    )
    workspace = runtime.workdir_host / "workspace"
    ok = out.exit_code == 0 and (workspace / workspace_output_name).is_file()
    if not ok:
        # Parent fallback workspace-only (still not mounting evaluation/)
        from bora.adapters.agent_codex import CodexExecutor

        ex = CodexExecutor(model=model)
        r = ex.invoke(prompt, timeout=timeout, workdir=str(workspace))
        ok2 = bool(r.ok and (workspace / workspace_output_name).is_file())
        return (
            ok2,
            1,
            {
                "ok": r.ok,
                "error": r.error,
                "executor_containment": "parent_fallback_after_container",
                "container_exit": out.exit_code,
                "container_stderr": (out.stderr_summary or "")[-500:],
            },
        )
    return (
        True,
        1,
        {
            "ok": True,
            "executor_containment": "container",
            "writer_stop": out.writer_stop_confirmed,
        },
    )


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
) -> tuple[bool, int, dict[str, Any]]:
    if os.environ.get("BORA_OFFLINE_AGENT") == "1" and not allow_offline:
        return False, 0, {"ok": False, "error": "offline_forced"}
    assert runtime.workdir_host is not None
    workspace = runtime.workdir_host / "workspace"

    # Prefer in-image CLI for first-party executors (L1 containment).
    if kind in {"codex", "pi", "opencode", "claude-code", "claude"}:
        ok, inv, meta = _run_builtin_cli_in_container(
            docker=docker,
            runtime=runtime,
            kind=kind if kind != "claude" else "claude-code",
            model=model,
            prompt=prompt,
            cred_root=cred_root,
            workspace_output_name="agent_result.json",
            timeout=180.0,
            api_key_env=api_key_env,
            base_url=base_url,
        )
        if ok:
            structured = _parse_json_from_text(
                str(meta.get("container_stdout") or meta.get("container_stdout_tail") or "")
            )
            if isinstance(structured, dict):
                (workspace / "agent_result.json").write_text(
                    json.dumps(structured, sort_keys=True) + "\n", encoding="utf-8"
                )
                return True, inv, {**meta, "model": model}
            # CLI exited 0 but no JSON — still fail closed for structured path.
            return (
                False,
                inv,
                {**meta, "ok": False, "error": "structured_missing"},
            )
        return ok, inv, meta

    from bora.adapters.agent_registry import resolve_executor

    try:
        ex = resolve_executor(
            kind, model=model, base_url=base_url, api_key=api_key_env
        )
    except KeyError:
        return False, 0, {"ok": False, "error": "executor_unknown"}
    # Inject projected key into env only for this process (not harness container).
    key_file = cred_root / "openai_api_key"
    old_key = os.environ.get("OPENAI_API_KEY")
    if key_file.is_file() and key_file.read_text(encoding="utf-8").strip():
        os.environ["OPENAI_API_KEY"] = key_file.read_text(encoding="utf-8").strip()
    try:
        result = ex.invoke(prompt, timeout=180.0, workdir=str(workspace))
    finally:
        if old_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = old_key
    if result.ok and isinstance(result.structured, dict):
        (workspace / "agent_result.json").write_text(
            json.dumps(result.structured, sort_keys=True) + "\n", encoding="utf-8"
        )
        return (
            True,
            1,
            {
                "ok": True,
                "model": result.model,
                "executor_containment": "parent_workspace_credential_scoped",
            },
        )
    if result.ok and result.text:
        # best-effort parse
        import json as _json
        import re

        structured = None
        try:
            structured = _json.loads(result.text)
        except Exception:
            m = re.search(r"\{.*\}", result.text, re.S)
            if m:
                try:
                    structured = _json.loads(m.group(0))
                except Exception:
                    structured = None
        if not isinstance(structured, dict):
            structured = None
        if isinstance(structured, dict):
            (workspace / "agent_result.json").write_text(
                json.dumps(structured, sort_keys=True) + "\n", encoding="utf-8"
            )
            return (
                True,
                1,
                {
                    "ok": True,
                    "model": result.model,
                    "executor_containment": "parent_workspace_credential_scoped",
                },
            )
    return (
        False,
        1,
        {
            "ok": False,
            "error": result.error or "agent_output_unstructured",
            "executor_containment": "parent_workspace_credential_scoped",
        },
    )


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
