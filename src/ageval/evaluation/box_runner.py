"""In-box evaluator runner. Executed by the box, not imported by the engine.

Reads one JSON request argument, loads the task's ``evaluator.py`` from the box
filesystem, calls the entrypoint, and prints the verdict as the last stdout line.

Every directory comes from the environment the box published, so this file never
needs to know whether it is running in a container or in a host work root. Only
the standard library is used, so any box image can host it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

RESULT_NAME = "evaluation.json"


def _maybe_agent() -> Any:
    """Harness Agent when the parent socket is projected; omit otherwise."""
    sock = os.environ.get("AGEVAL_AGENT_SERVICE_SOCK", "").strip()
    attempt_id = os.environ.get("AGEVAL_ATTEMPT_ID", "").strip()
    if not sock or not attempt_id:
        return None
    try:
        from ageval_sdk import Agent
    except ImportError:
        return None
    return Agent(attempt_id=attempt_id)


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


def _published(artifacts_dir: Path) -> dict[str, str]:
    """Artifact id → in-box path for what the task actually produced."""
    if not artifacts_dir.is_dir():
        return {}
    return {
        item.stem: str(item)
        for item in sorted(artifacts_dir.iterdir())
        if item.is_file() and item.name != RESULT_NAME
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(json.dumps({"status": "ERROR", "error": "missing_request"}))
        return 2
    request = json.loads(argv[1])
    here = Path(__file__).resolve().parent
    func = _load_callable(here / str(request["module_file"]), str(request["entrypoint"]))

    artifacts_dir = Path(os.environ["AGEVAL_ARTIFACTS"])
    # Judge from the artifacts directory: relative paths in an evaluator mean
    # "the thing the task produced".
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(artifacts_dir)
    inputs: dict[str, Any] = {
        "artifacts": _published(artifacts_dir),
        "artifacts_dir": str(artifacts_dir),
        "workspace_dir": os.environ["AGEVAL_WORKSPACE"],
        "evaluation_dir": os.environ["AGEVAL_EVALUATION"],
        "inputs": request.get("inputs") or [],
        "parameters": request.get("parameters") or {},
    }
    agent = _maybe_agent()
    if agent is not None:
        inputs["agent"] = agent
    verdict = func(inputs)
    if not isinstance(verdict, dict):
        print(json.dumps({"status": "ERROR", "error": "verdict_not_object"}))
        return 1
    payload = json.dumps(verdict, sort_keys=True, ensure_ascii=False)
    (artifacts_dir / RESULT_NAME).write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
