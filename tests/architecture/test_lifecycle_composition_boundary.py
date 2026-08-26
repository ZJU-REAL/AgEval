"""Architecture boundaries for Lifecycle v0.2."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def test_src_does_not_import_tests() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "import tests" in stripped or "from tests" in stripped:
                offenders.append(f"{path}:{stripped}")
    assert offenders == []


def test_composition_has_no_lifecycle_double() -> None:
    composition = (SRC / "ageval" / "application" / "composition.py").read_text(encoding="utf-8")
    assert "ScriptedLifecycleStages" not in composition
    assert "lifecycle_stages" not in composition
    cli = SRC / "ageval" / "cli"
    offenders: list[str] = []
    for path in cli.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "ScriptedLifecycleStages" in text or "tests.doubles" in text:
            offenders.append(str(path.relative_to(SRC)))
    assert offenders == []


def test_cli_has_lock_and_run() -> None:
    from typer.main import get_command
    from typer.testing import CliRunner

    from ageval.cli.main import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "lock" in result.stdout
    # v0.6+ exposes product run; v0.2 composition still does not wire stage doubles.
    assert "run" in result.stdout
    result2 = CliRunner().invoke(app, ["lock", "--help"])
    assert result2.exit_code == 0
    result3 = CliRunner().invoke(app, ["run", "--help"])
    assert result3.exit_code == 0
    commands = getattr(get_command(app), "commands", None)
    assert isinstance(commands, dict)
    run = commands.get("run")
    assert run is not None
    opts = {opt for param in run.params for opt in param.opts}
    assert "--dir" in opts
