"""ACP lock snapshot contains no secrets or absolute host paths."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw


def test_acp_lock_snapshot_is_safe(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    doc = {
        "format": "bora.task/1",
        "task_id": "t",
        "harness": {"runtime": "python", "entrypoint": "harness:run"},
        "parameters": {},
        "provider": {"kind": "local", "assurance": "l0"},
        "agent_profiles": [
            {
                "id": "p",
                "executor": "acp",
                "model": "entry-default",
                "options": {"entry": "codex"},
                "api_key": "OPENAI_API_KEY",
            }
        ],
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
    (pkg / "bora.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    (pkg / "harness.py").write_text("async def run(ctx): pass\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text(
        "def evaluate(i): return {'status':'PASS','score':1}\n", encoding="utf-8"
    )
    lock = ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        pkg, "t", capabilities=DeclarationCapabilityCatalog()
    )
    payload = json.dumps(thaw(lock.agent_profiles), sort_keys=True)
    assert "sk-" not in payload
    assert "/Users/" not in payload
    assert "/home/" not in payload
    assert "OPENAI_API_KEY" in payload  # locator ok
    snap = thaw(lock.agent_profiles)[0]["options"]["_acp_lock"]
    assert snap["descriptor_digest"].startswith("sha256:")
    assert "credential" not in json.dumps(snap).lower() or "credential_env" in json.dumps(
        snap
    )
