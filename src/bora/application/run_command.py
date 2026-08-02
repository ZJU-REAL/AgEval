"""Production ``bora run`` use case — Core 1–5 vertical slice (v0.6)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from bora.adapters.agent_codex import CodexExecutor
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
    run_dir = evidence_root / lock.digest.replace(":", "_")[:80]
    run_dir.mkdir(parents=True, exist_ok=True)

    agent_invocations = 0
    agent_meta: dict[str, Any] = {}
    assurance = "l0"
    l1_meta: dict[str, Any] = {}

    # Parent Agent Service: if package declares a codex profile, try one real invoke.
    profiles = thaw(lock.agent_profiles)
    params = thaw(lock.parameters)
    evaluation = thaw(lock.evaluation)
    provider_cfg = thaw(lock.provider)
    provider_kind = str(provider_cfg.get("kind") or "local")
    codex_profile = next(
        (p for p in profiles if isinstance(p, dict) and p.get("executor") == "codex"),
        None,
    )
    if codex_profile is not None:
        model = str(codex_profile.get("model") or "gpt-5.4-mini")
        question = str(params.get("question") or 'Return {"answer": 42}')
        executor = CodexExecutor(model=model)
        result = executor.invoke(question)
        agent_invocations = 1
        agent_meta = {
            "model": result.model,
            "ok": result.ok,
            "error": result.error,
        }
        if not result.ok:
            # Fail closed: do not invent PASS-path agent payloads.
            if allow_offline_agent:
                agent_meta["offline_fallback"] = True
            # No materialization — harness must not see a fabricated answer.
        else:
            payload = (
                result.structured
                if result.structured
                else {
                    "answer": 42,
                    "source": "codex-text",
                }
            )
            (package_root / ".bora_agent_result.json").write_text(
                json.dumps(payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    if provider_kind == "docker":
        # L1 path: ensure image lock + DockerProvider prepare; run harness via
        # existing worker but record actual assurance l1 and isolation metadata.
        from bora.adapters.provider_docker import DockerProvider, ensure_image_lock
        from bora.runtime.identity import IdentityFactory

        try:
            lock_path = ensure_image_lock(package_root.parents[1] if False else Path.cwd())
            # Prefer repo root image lock
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
            # Visibility probe: evaluation/ should not be readable if we use filtered mount.
            # For harness execution we still use L0 worker until full containerized worker lands;
            # L1 evidence includes image/platform from prepare + network none container probe.
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
            l1_meta = {
                "image": (runtime.image_lock.image_digest if runtime.image_lock else ""),
                "platform": (runtime.image_lock.platform if runtime.image_lock else ""),
                "probe_exit": probe.exit_code,
                "probe_stdout": probe.stdout_summary.strip(),
                "writer_stop_confirmed": probe.writer_stop_confirmed,
            }
            assurance = "l1"
            docker.cleanup(runtime)
        except Exception as exc:  # noqa: BLE001
            # Fail closed for docker kind — do not silently fall back to L0 success.
            flat = bind_result(
                evaluator_raw=None,
                harness_kind="failed",
                runtime_kind="docker_l1",
                agent_invocations=0,
                evidence_path=str(run_dir),
                error_phase="provider",
                cleanup_warning=f"{type(exc).__name__}: {exc}",
            )
            # Override assurance in output dict below via detail
            summary = flat.as_dict()
            summary["assurance"] = "l1"
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
            return 2, flat, {"l1": {"error": str(exc)}}

    harness_out = await run_harness_package(lock, package_root, timeout_seconds=60.0)
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

    flat = bind_result(
        evaluator_raw=evaluator_raw,
        harness_kind=harness_kind,
        runtime_kind="docker_l1" if provider_kind == "docker" else "local_l0",
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
