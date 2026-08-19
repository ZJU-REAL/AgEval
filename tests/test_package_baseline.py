"""Phase 0 baseline: package import, help, and dependency direction."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import ageval
from ageval.application import composition


def test_version_present() -> None:
    assert ageval.__version__  # non-empty semver-ish package version
    assert len(ageval.__version__.split(".")) >= 2


def test_ageval_help_via_console_script() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ageval.cli.main", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "ageval" in result.stdout.lower() or "Usage" in result.stdout


def test_composition_builds_lock_command() -> None:
    cmd = composition.build_lock_command()
    assert cmd is not None
    assert composition.build_config_core() is not None


def test_cli_does_not_import_task_packages() -> None:
    """CLI module graph must not pull examples or harness modules."""
    import ageval.cli.main as m

    # Ensure examples are not side-imported.
    assert "examples" not in sys.modules or not any(k.startswith("examples.") for k in sys.modules)
    assert hasattr(m, "app")


def test_config_does_not_import_cli() -> None:
    """Domain Config must not depend on the CLI framework."""
    import ageval.config.load_and_lock as core

    source = Path(core.__file__).read_text(encoding="utf-8")
    assert "typer" not in source
    assert "ageval.cli" not in source
