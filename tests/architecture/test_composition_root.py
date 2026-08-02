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
    source = Path(cli_main.__file__).read_text(encoding="utf-8")
    assert "build_run_task" in source
    assert "from bora.application.composition import build_run_task" in source
    # Direct use-case import is forbidden on the public run path (B-04).
    assert "from bora.application.run_command import run_task" not in source


def test_cli_campaign_uses_composition() -> None:
    source = Path(cli_main.__file__).read_text(encoding="utf-8")
    assert "build_campaign_runner" in source
    assert "from bora.application.campaign import run_campaign" not in source
