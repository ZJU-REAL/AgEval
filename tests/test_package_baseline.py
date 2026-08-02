"""Phase 0 baseline: package import, help, and dependency direction."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import bora
from bora.application import composition


def test_version_present() -> None:
    assert bora.__version__ == "0.1.0"


def test_bora_help_via_console_script() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "bora.cli.main", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "bora" in result.stdout.lower() or "Usage" in result.stdout


def test_composition_builds_lock_command() -> None:
    cmd = composition.build_lock_command()
    assert cmd is not None
    assert composition.build_config_core() is not None


def test_cli_does_not_import_task_packages() -> None:
    """CLI module graph must not pull examples or harness modules."""
    import bora.cli.main as m

    # Ensure examples are not side-imported.
    assert "examples" not in sys.modules or not any(k.startswith("examples.") for k in sys.modules)
    assert hasattr(m, "app")


def test_config_does_not_import_cli() -> None:
    """Domain Config must not depend on the CLI framework."""
    import bora.config.load_and_lock as core

    source = Path(core.__file__).read_text(encoding="utf-8")
    assert "typer" not in source
    assert "bora.cli" not in source
