"""Expected-failure matrix for ACP (lock/preflight; no silent private fallback)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bora.adapters.agent_acp import AcpExecutor
from bora.adapters.agent_registry import resolve_executor
from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore

REPO = Path(__file__).resolve().parents[2]


def test_unknown_entry_lock_fails(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "task.yaml").write_text(
        """
format: bora.task/1
task_id: t
harness: {runtime: python, entrypoint: harness:run}
parameters: {}
provider: {kind: local, assurance: l0}
agent_profiles:
  - id: bad
    executor: acp
    model: m
    options: {entry: not-registered}
limits: {wall_time_seconds: 10, agent_invocations: 1, environment_actions: 0}
artifacts: {publishable: []}
evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs: []
  output: {format: json}
""",
        encoding="utf-8",
    )
    (pkg / "harness.py").write_text("async def run(ctx): pass\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text(
        "def evaluate(i): return {'status':'PASS','score':1}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
            pkg, "t", capabilities=DeclarationCapabilityCatalog()
        )


def test_private_kind_resolve_fails_closed() -> None:
    with pytest.raises(KeyError):
        resolve_executor("codex", model="x")


def test_adapter_missing_readiness_no_host_fallback(monkeypatch: object) -> None:
    """Mode 1 adapter missing → readiness adapter-missing; no private invoke."""
    from bora.adapters.acp_registry import get_entry, readiness_for

    desc = get_entry("codex")
    assert desc is not None

    def which(name: str) -> str | None:
        if name == "codex":
            return "/fake/codex"
        return None

    row = readiness_for(desc, which=which)
    assert row["readiness"] == "adapter-missing"
    os.environ["BORA_OFFLINE_AGENT"] = "0"
    # Executor still constructs but host readiness fails at ensure_session.
    ex = AcpExecutor(entry_id="codex", model="entry-default")
    # Force host path probe by ensuring no command_override
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "bora.adapters.agent_acp.readiness_for",
        lambda *_a, **_k: row,
    )
    r = ex.invoke("hi", timeout=5)
    assert r.ok is False
    assert "adapter_missing" in str(r.error) or "adapter-missing" in str(r.error).replace("_", "-")


def test_offline_cli_subprocess_nonzero() -> None:
    env = os.environ.copy()
    env["BORA_OFFLINE_AGENT"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "bora.cli.main",
            "run",
            str(REPO / "examples/core"),
            "--task",
            "builtin-executor-conformance",
            "--set",
            '/parameters/active_profile="opencode-mini"',
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=120,
    )
    assert proc.returncode != 0
    # Must not claim PASS
    out = (proc.stdout or "") + (proc.stderr or "")
    if out.strip().startswith("{"):
        try:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            assert data.get("status") != "PASS"
        except json.JSONDecodeError:
            pass
