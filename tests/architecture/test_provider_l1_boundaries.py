"""L1: CLI/domain must not import Docker SDK; adapters have no bench branches."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cli_does_not_import_docker_sdk() -> None:
    cli_dir = ROOT / "src" / "ageval" / "cli"
    text = "\n".join(p.read_text(encoding="utf-8") for p in cli_dir.glob("*.py"))
    assert "import docker" not in text
    assert "from docker" not in text


def test_provider_docker_no_benchmark_branches() -> None:
    pkg = ROOT / "src" / "ageval" / "adapters" / "provider_docker"
    text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(pkg.rglob("*.py")))
    for banned in ("terminal-bench", "TerminalBench", "multiagentbench", "tau2"):
        assert banned not in text
