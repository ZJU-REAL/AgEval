"""Spec 05 Phase 3: NooaContainerExecutor + worker pure unit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from ageval.provider.outcomes import ProcessOutcome, ProcessTerminalKind
from ageval.runtime.identity import IdentityFactory

_NOOA_SRC = Path(__file__).resolve().parents[2] / "plugins" / "nooa" / "src"
if str(_NOOA_SRC) not in sys.path:
    sys.path.insert(0, str(_NOOA_SRC))

from nooa_plugin.container import NooaContainerExecutor  # noqa: E402


def test_nooa_container_executor_parses_worker_stdout() -> None:
    payload = {
        "model": "nooa",
        "text": '{"ok":true}',
        "structured": {"ok": True},
        "ok": True,
        "error": None,
        "metadata": {"plugin": "nooa", "execution_location": "attempt-container"},
    }

    def fake_supervise(argv, **kwargs):  # noqa: ANN001, ANN003
        del argv, kwargs
        factory = IdentityFactory()
        attempt = factory.new_attempt(factory.new_trial(factory.new_run(), "sha256:" + "n" * 64))
        return ProcessOutcome(
            attempt=attempt,
            assurance="l0",
            terminal=ProcessTerminalKind.EXITED,
            exit_code=0,
            signal=None,
            stdout_summary=json.dumps(payload) + "\n",
            stderr_summary="",
            truncated=False,
            pid=None,
            pgid=None,
            writer_stop_confirmed=True,
            cleanup_ok=True,
        )

    ex = NooaContainerExecutor(
        container_id="cid123",
        agent_ref="lib.agents:JsonlAggAgent",
        method="run",
        uid=10001,
        gid=10001,
    )
    with patch("nooa_plugin.container.supervise_docker_cli", side_effect=fake_supervise):
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
        / "ageval_executor_nooa.py"
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
