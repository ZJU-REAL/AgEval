"""L0 package evaluator worker — dedicated subprocess (not parent import)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def run_evaluator_worker(
    package_root: Path,
    lock: Any,
    artifacts_map: dict[str, str],
    *,
    database_root: Path | None = None,
) -> dict[str, Any]:
    """Run package evaluator in a dedicated subprocess (not parent import)."""
    _ = lock  # reserved for future lock-scoped evaluator options
    path = package_root / "evaluator.py"
    if not path.is_file():
        return {"status": "ERROR", "score": None, "metrics": {}}
    # #68: [task_dir, database_root] — same contract as harness worker.
    # Do not inject shared/lib leaf; authors use shared.lib.* / lib.*.
    # Build highest-priority first, then reverse-insert so final path prefix
    # is [task_dir, database_root, ...] (insert(0) reverses forward iteration).
    path_entries: list[str] = [str(package_root.resolve())]
    if database_root is not None:
        path_entries.append(str(database_root.resolve()))
    path_inject = repr(path_entries)
    with tempfile.TemporaryDirectory(prefix="bora-eval-") as tmp:
        script = Path(tmp) / "run_eval.py"
        out_path = Path(tmp) / "out.json"
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
        proc = subprocess.run(
            [sys.executable, str(script)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=child_env,
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
