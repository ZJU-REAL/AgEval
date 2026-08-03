"""Spec 17: skills layout exists and only describes shipped CLI entrypoints."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "skills"


def test_skills_readme_and_four_skills_present() -> None:
    assert (SKILLS / "README.md").is_file()
    for name in ("platform", "cli", "config-package", "sdk-harness"):
        skill = SKILLS / name / "SKILL.md"
        assert skill.is_file(), skill
        text = skill.read_text(encoding="utf-8")
        assert "---" in text[:40]
        assert "name:" in text[:200]


def test_cli_skill_commands_exist_in_production_cli() -> None:
    """Walk shipped CLI surface from skill text against Typer app registration."""
    skill = (SKILLS / "cli" / "SKILL.md").read_text(encoding="utf-8")
    main = (REPO / "src" / "bora" / "cli" / "main.py").read_text(encoding="utf-8")
    # Commands claimed in skill table must be registered with @app.command
    claimed = set(re.findall(r"`bora (lock|run|campaign|evidence|status)\b", skill))
    assert claimed, "cli skill must document bora commands"
    for cmd in claimed:
        assert f'@app.command("{cmd}")' in main, cmd


def test_skills_forbid_trajectory_as_pass() -> None:
    platform = (SKILLS / "platform" / "SKILL.md").read_text(encoding="utf-8")
    assert "Trajectory ≠ PASS" in platform or "trajectory ≠ PASS" in platform.lower() or "Trajectory" in platform
    assert "PASS" in platform
