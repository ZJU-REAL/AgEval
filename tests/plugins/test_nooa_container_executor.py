"""Spec 05 Phase 3: NooaContainerExecutor + worker pure unit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from bora.adapters.nooa_container import NooaContainerExecutor


def test_nooa_container_executor_parses_worker_stdout() -> None:
    payload = {
        "model": "nooa",
        "text": '{"ok":true}',
        "structured": {"ok": True},
        "ok": True,
        "error": None,
        "metadata": {"plugin": "nooa", "execution_location": "attempt-container"},
    }

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        del cmd, kwargs
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload) + "\n", stderr=""
        )

    ex = NooaContainerExecutor(
        container_id="cid123",
        agent_ref="lib.agents:JsonlAggAgent",
        method="run",
        uid=10001,
        gid=10001,
    )
    with patch("bora.adapters.nooa_container.subprocess.run", side_effect=fake_run):
        result = ex.invoke("do it", timeout=5.0)
    assert result.ok
    assert result.metadata is not None
    assert result.metadata.get("execution_location") == "attempt-container"
    assert result.metadata.get("plugin") == "nooa"


def test_worker_script_loads_agent(tmp_path: Path) -> None:
    """Run the stdlib worker against a tiny package tree (no docker)."""
    pkg = tmp_path / "pkg"
    (pkg / "lib").mkdir(parents=True)
    (pkg / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "lib" / "agents.py").write_text(
        "class A:\n"
        "    def run(self, prompt, workdir=None):\n"
        "        return {'ok': True, 'text': 'hi', 'structured': {'prompt': prompt}}\n",
        encoding="utf-8",
    )
    worker = (
        Path(__file__).resolve().parents[2]
        / "plugins"
        / "nooa"
        / "worker"
        / "bora_executor_nooa.py"
    )
    req = {
        "prompt": "p",
        "agent": "lib.agents:A",
        "method": "run",
        "package_root": str(pkg),
        "workdir": str(tmp_path),
    }
    proc = subprocess.run(
        ["python3", str(worker)],
        input=json.dumps(req),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout.strip().splitlines()[-1])
    assert doc["ok"] is True
    assert doc["metadata"]["execution_location"] == "attempt-container"
