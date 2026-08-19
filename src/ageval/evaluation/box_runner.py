"""In-box evaluator runner. Executed by the box, not imported by the engine.

Reads one JSON request argument, loads the task's ``evaluator.py`` from the box
filesystem, calls the entrypoint, and prints the verdict as the last stdout line.
Runs with only the standard library so any box image can host it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _load_callable(module_path: Path, entrypoint: str) -> Any:
    module_name, _, func_name = entrypoint.partition(":")
    if not module_name or not func_name:
        raise ValueError(f"invalid entrypoint: {entrypoint}")
    spec = importlib.util.spec_from_file_location("ageval_task_evaluator", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load evaluator module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ageval_task_evaluator"] = module
    spec.loader.exec_module(module)
    func = getattr(module, func_name, None)
    if func is None:
        raise AttributeError(f"evaluator entrypoint missing: {entrypoint}")
    return func


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(json.dumps({"status": "ERROR", "error": "missing_request"}))
        return 2
    request = json.loads(argv[1])
    here = Path(__file__).resolve().parent
    module_path = here / str(request.get("module_file") or "evaluator.py")
    func = _load_callable(module_path, str(request["entrypoint"]))

    context = {
        "artifacts": request.get("artifacts") or {},
        "artifacts_dir": request.get("artifacts_dir"),
        "evaluation_dir": request.get("evaluation_dir"),
        "inputs": request.get("inputs") or [],
        "parameters": request.get("parameters") or {},
    }
    verdict = func(context)
    if not isinstance(verdict, dict):
        print(json.dumps({"status": "ERROR", "error": "verdict_not_object"}))
        return 1
    result_path = request.get("result_path")
    if result_path:
        Path(str(result_path)).write_text(
            json.dumps(verdict, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
    print(json.dumps(verdict, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
