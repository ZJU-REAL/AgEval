"""ACP lock snapshot contains no secrets or absolute host paths."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ageval.adapters.package_fs import LocalPackageReader
from ageval.config.capabilities import DeclarationCapabilityCatalog
from ageval.config.load_and_lock import ConfigCore
from ageval.config.model import thaw


def test_acp_lock_snapshot_is_safe(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    doc = {
        "format": "ageval.task/1",
        "task_id": "t",
        "harness": {"runtime": "python", "entrypoint": "harness:run"},
        "parameters": {},
        "provider": {"kind": "local", "assurance": "l0"},
        "agent_profiles": [{"id": "p"}],
        "limits": {
            "wall_time_seconds": 10,
            "agent_invocations": 1,
            "environment_actions": 0,
        },
        "artifacts": {"publishable": []},
        "evaluation": {
            "runtime": "python",
            "entrypoint": "evaluator:evaluate",
            "network": "none",
            "inputs": [],
            "output": {"format": "json"},
        },
    }
    (pkg / "task.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    (pkg / "harness.py").write_text("async def run(ctx): pass\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text(
        "def evaluate(i): return {'status':'PASS','score':1}\n", encoding="utf-8"
    )
    lock = ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        pkg,
        "t",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings={
            "p": {
                "executor": "acp",
                "model": "entry-default",
                "extensions": [{"plugin": "acp", "options": {"entry": "codex"}}],
                "api_key": "${OPENAI_API_KEY}",
            }
        },
    )
    payload = json.dumps(thaw(lock.agent_profiles), sort_keys=True)
    assert "sk-" not in payload
    assert "/Users/" not in payload
    assert "/home/" not in payload
    assert "OPENAI_API_KEY" in payload  # locator ok
    opts = thaw(lock.agent_profiles)[0]["extensions"][0]["options"]
    assert opts["entry"] == "codex"
    assert "_acp_lock" not in opts
