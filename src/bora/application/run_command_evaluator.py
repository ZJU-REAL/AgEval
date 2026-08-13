"""L0 package evaluator worker — dedicated subprocess (not parent import)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from bora.adapters.provider_local import LocalProcessProvider
from bora.config.model import thaw
from bora.provider.contract import ExecutableGrant, ProcessLaunchPlan
from bora.provider.outcomes import ProcessTerminalKind
from bora.provider.workspace_plan import WorkspacePlan
from bora.runtime.identity import AttemptIdentity, IdentityFactory

# Conservative fallback when lock limits omit / cannot supply wall_time_seconds.
_DEFAULT_EVALUATOR_TIMEOUT_SECONDS = 60.0


def _evaluator_timeout_seconds(lock: Any) -> float:
    """Derive evaluator wall timeout from locked limits (same read as harness)."""
    try:
        limits = getattr(lock, "limits", None)
        if limits is None:
            return _DEFAULT_EVALUATOR_TIMEOUT_SECONDS
        wall_s = float(thaw(limits).get("wall_time_seconds") or 0)
    except Exception:
        return _DEFAULT_EVALUATOR_TIMEOUT_SECONDS
    return wall_s if wall_s > 0 else _DEFAULT_EVALUATOR_TIMEOUT_SECONDS


def run_evaluator_worker(
    package_root: Path,
    lock: Any,
    artifacts_map: dict[str, str],
    *,
    database_root: Path | None = None,
    attempt: AttemptIdentity | None = None,
) -> dict[str, Any]:
    """Run package evaluator in a dedicated subprocess (not parent import).

    Returns evaluator raw facts only. PASS binding stays in evaluation/result_binding.
    """
    path = package_root / "evaluator.py"
    if not path.is_file():
        return {"status": "ERROR", "score": None, "metrics": {}}
    timeout = _evaluator_timeout_seconds(lock)
    # #68: [task_dir, database_root] — same contract as harness worker.
    # Do not inject shared/lib leaf; authors use shared.lib.* / lib.*.
    # Build highest-priority first, then reverse-insert so final path prefix
    # is [task_dir, database_root, ...] (insert(0) reverses forward iteration).
    path_entries: list[str] = [str(package_root.resolve())]
    if database_root is not None:
        path_entries.append(str(database_root.resolve()))
    path_inject = repr(path_entries)
    with tempfile.TemporaryDirectory(prefix="bora-eval-") as tmp:
        tmp_path = Path(tmp)
        script = tmp_path / "run_eval.py"
        out_path = tmp_path / "out.json"
        work_base = tmp_path / "provider"
        work_base.mkdir()
        script.write_text(
            "\n".join(
                [
                    "import json, importlib.util, sys",
                    f"for _p in reversed({path_inject}):",
                    "    if _p in sys.path:",
                    "        sys.path.remove(_p)",
                    "    sys.path.insert(0, _p)",
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
        child_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        if database_root is not None:
            child_env["BORA_DATABASE_ROOT"] = str(database_root.resolve())

        if attempt is None:
            factory = IdentityFactory()
            digest = getattr(lock, "digest", None) or ("sha256:" + "e" * 64)
            run = factory.new_run()
            trial = factory.new_trial(run, str(digest))
            attempt = factory.new_attempt(trial)
        plan = ProcessLaunchPlan(
            attempt=attempt,
            workspace=WorkspacePlan(attempt=attempt, base_dir=work_base, relative_workdir="ws"),
            executable=ExecutableGrant(path=Path(sys.executable)),
            argv=(sys.executable, str(script)),
            env=child_env,
            timeout_seconds=timeout,
        )
        outcome = LocalProcessProvider().execute_sync(plan)
        stderr_tail = (outcome.stderr_summary or "")[-500:]
        if outcome.terminal == ProcessTerminalKind.TIMED_OUT:
            return {
                "status": "ERROR",
                "score": None,
                "metrics": {
                    "error": "evaluator_timeout",
                    "timeout_seconds": timeout,
                    "stderr": stderr_tail,
                },
            }
        if (
            outcome.terminal != ProcessTerminalKind.EXITED
            or outcome.exit_code != 0
            or not out_path.is_file()
        ):
            return {
                "status": "ERROR",
                "score": None,
                "metrics": {"stderr": stderr_tail},
            }
        raw = json.loads(out_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"status": "ERROR", "score": None, "metrics": {}}
        return raw
