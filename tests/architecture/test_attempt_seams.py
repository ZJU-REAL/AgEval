"""Lock Attempt identity, LifecycleStages, and composition seams."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "bora"


def test_l0_production_uses_coordinator() -> None:
    text = (SRC / "application" / "attempt" / "run_command.py").read_text(encoding="utf-8")
    assert "run_lifecycle" in text
    assert "LocalL0Stages" in text
    assert "DockerL1Stages" in text


def test_stage_cleanup_is_not_empty_fact() -> None:
    text = (SRC / "application" / "attempt" / "attempt_stages.py").read_text(encoding="utf-8")
    assert "cleanup_l0" in text
    assert "cleanup_l1" in text or "_l1_host_cleanup" in text
    tree = ast.parse(text)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name not in {"LocalL0Stages", "DockerL1Stages"}:
            continue
        cleanup = next(
            (
                n
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "cleanup"
            ),
            None,
        )
        assert cleanup is not None, node.name
        src = ast.get_source_segment(text, cleanup) or ""
        assert "return _fact" not in src or "cleanup_l0" in src or "cleanup_l1" in src


def test_cli_imports_only_composition() -> None:
    cli = SRC / "cli"
    offenders: list[str] = []
    for path in cli.glob("*.py"):
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


def test_bora_runs_layout_owned_by_evidence() -> None:
    offenders: list[str] = []
    needle = '/ ".bora" / "runs"'
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC)
        if rel.parts[0] == "evidence":
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if needle in s or s.replace("'", '"').find('/ ".bora" / "runs"') >= 0:
                offenders.append(f"{rel}:{i}:{s}")
    assert offenders == []


def test_attempt_package_defines_new_run_once() -> None:
    text = (SRC / "application" / "attempt" / "run_command.py").read_text(encoding="utf-8")
    assert text.count(".new_run(") == 1


def test_queries_own_single_releases_ddl() -> None:
    queries = (REPO / "services" / "registry" / "queries.py").read_text(encoding="utf-8")
    assert queries.count("CREATE TABLE IF NOT EXISTS releases") == 1
    adapter = (REPO / "services" / "registry" / "sql_adapter.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS releases" not in adapter
