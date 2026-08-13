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


def _stage_method_src(text: str, class_name: str, method: str) -> str:
    tree = ast.parse(text)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        fn = next(
            (
                n
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method
            ),
            None,
        )
        assert fn is not None, f"{class_name}.{method}"
        return ast.get_source_segment(text, fn) or ""
    raise AssertionError(class_name)


def test_evaluate_and_bind_are_not_empty_markers() -> None:
    text = (SRC / "application" / "attempt" / "attempt_stages.py").read_text(encoding="utf-8")
    pairs = (
        ("LocalL0Stages", "evaluate", "evaluate_l0"),
        ("LocalL0Stages", "bind", "bind_l0_result"),
        ("DockerL1Stages", "evaluate", "evaluate_l1"),
        ("DockerL1Stages", "bind", "bind_l1_result"),
    )
    for cls, method, needle in pairs:
        src = _stage_method_src(text, cls, method)
        assert needle in src, f"{cls}.{method} must call {needle}"
        assert "return _fact" not in src or needle in src


def test_assemble_quota_object_is_shared_in_source() -> None:
    text = (SRC / "application" / "attempt" / "agent_service_assemble.py").read_text(
        encoding="utf-8"
    )
    assert "quota = AgentInvocationQuota" in text
    assert "ParentAgentService(" in text
    assert "AttemptCapabilityAuthority(" in text
    assert '"invoke_quota": quota' in text
    assert "invoke_quota=quota" in text


def test_handler_calls_all_domain_services() -> None:
    app = (REPO / "services" / "registry" / "app.py").read_text(encoding="utf-8")
    for needle in ("state.packages.", "state.results.", "state.orgs.", "state.auth."):
        assert needle in app, needle


def test_handler_methods_do_not_touch_store() -> None:
    text = (REPO / "services" / "registry" / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    handler = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "make_handler":
            handler = next(
                (n for n in ast.walk(node) if isinstance(n, ast.ClassDef) and n.name == "Handler"),
                None,
            )
            break
    assert handler is not None
    src = ast.get_source_segment(text, handler) or ""
    assert "state.meta." not in src
    assert "state.blobs." not in src


def test_bearer_is_only_used_by_dispatch() -> None:
    text = (REPO / "services" / "registry" / "app.py").read_text(encoding="utf-8")
    assert text.count("_bearer(") == 2


def test_store_has_no_sql_literals() -> None:
    text = (REPO / "services" / "registry" / "store.py").read_text(encoding="utf-8")
    needles = ("DELETE FROM", "INSERT INTO", "CREATE TABLE", "UPDATE ")
    offenders: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if any(n in line for n in needles):
            offenders.append(f"{i}:{stripped}")
    assert offenders == []


def test_registry_ops_have_no_private_client_helpers() -> None:
    root = SRC / "application" / "registry_ops"
    for path in root.glob("*_command.py"):
        text = path.read_text(encoding="utf-8")
        assert "def _client(" not in text, path.name
        if path.name != "client.py":
            assert "RegistryClient(" not in text, path.name
    results = (root / "results_command.py").read_text(encoding="utf-8")
    assert "suite.suite_metrics" not in results
