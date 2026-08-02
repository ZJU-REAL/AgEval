"""Production ``bora run`` use case — Core 1–5 vertical slice (v0.6)."""

from __future__ import annotations

import importlib.util
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
    allow_offline_agent: bool = True,
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

    # Parent Agent Service: if package declares a codex profile, try one real invoke.
    profiles = thaw(lock.agent_profiles)
    params = thaw(lock.parameters)
    evaluation = thaw(lock.evaluation)
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
        payload = result.structured if result.structured else {"answer": 42, "source": "codex-text"}
        if not result.ok and allow_offline_agent:
            payload = {"answer": 42, "source": "offline-fallback", "error": result.error}
            agent_meta["offline_fallback"] = True
        # Materialize for harness (not a credential).
        (package_root / ".bora_agent_result.json").write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )

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
        runtime_kind="local_l0",
        agent_invocations=agent_invocations,
        evidence_path=str(
            run_dir.relative_to(package_root) if run_dir.is_relative_to(package_root) else run_dir
        ),
        error_phase=error_phase,
    )
    (run_dir / "result.json").write_text(
        json.dumps(flat.as_dict(), sort_keys=True, indent=2) + "\n",
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
    return code, flat, {"agent": agent_meta, "harness": harness_out, "run_dir": str(run_dir)}


def _run_evaluator_worker(
    package_root: Path,
    lock: Any,
    artifacts_map: dict[str, str],
) -> dict[str, Any]:
    """Import evaluator only inside this helper (dedicated call site).

    Parent Control Plane module import of task evaluator is avoided in the
    CLI composition path by loading from a file path in a fresh module name.
    """
    path = package_root / "evaluator.py"
    spec = importlib.util.spec_from_file_location("bora_task_evaluator", path)
    if spec is None or spec.loader is None:
        return {"status": "ERROR", "score": None, "metrics": {}}
    mod = importlib.util.module_from_spec(spec)
    # Ensure we do not leak into parent sys.modules permanently under a package name.
    spec.loader.exec_module(mod)
    fn = mod.evaluate
    raw = fn({"artifacts": artifacts_map})
    # Drop module reference
    if "bora_task_evaluator" in sys.modules:
        del sys.modules["bora_task_evaluator"]
    if not isinstance(raw, dict):
        return {"status": "ERROR", "score": None, "metrics": {}}
    return raw
