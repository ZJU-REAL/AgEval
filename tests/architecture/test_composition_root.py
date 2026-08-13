"""CLI must assemble run/campaign through the production composition root."""

from __future__ import annotations

import inspect
from pathlib import Path

from bora.application import composition
from bora.cli import main as cli_main


def test_build_run_task_returns_callable() -> None:
    run_task = composition.build_run_task()
    assert callable(run_task)
    assert inspect.iscoroutinefunction(run_task)


def test_cli_run_uses_composition_not_direct_run_command() -> None:
    # Commands live in cmd_* modules after chore #31 split; scan CLI package.
    cli_dir = Path(cli_main.__file__).resolve().parent
    sources = "\n".join(p.read_text(encoding="utf-8") for p in cli_dir.glob("*.py"))
    assert "build_run_task" in sources
    assert "from bora.application.composition import build_run_task" in sources
    # Direct use-case import is forbidden on the public run path (B-04).
    assert "from bora.application.attempt.run_command import run_task" not in sources


def test_cli_campaign_uses_composition() -> None:
    cli_dir = Path(cli_main.__file__).resolve().parent
    sources = "\n".join(p.read_text(encoding="utf-8") for p in cli_dir.glob("*.py"))
    assert "build_campaign_runner" in sources
    assert "from bora.application.attempt.campaign import run_campaign" not in sources


def test_cli_imports_composition_only() -> None:
    cli_dir = Path(cli_main.__file__).resolve().parent
    offenders: list[str] = []
    for path in cli_dir.glob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "bora.application." not in stripped:
                continue
            if "bora.application.composition" in stripped:
                continue
            offenders.append(f"{path.name}:{i}:{stripped}")
    assert offenders == []
