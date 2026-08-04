"""Architecture gate: one ACP client, no vendor stdout scrape in ACP path."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTERS = REPO / "src" / "bora" / "adapters"


def test_single_acp_executor_module() -> None:
    acp_modules = list(ADAPTERS.glob("agent_acp*.py"))
    assert acp_modules == [ADAPTERS / "agent_acp.py"]


def test_acp_module_has_no_regex_json_scrape() -> None:
    src = (ADAPTERS / "agent_acp.py").read_text(encoding="utf-8")
    # Forbidden patterns from Spec 19 red lines.
    assert "_try_parse_structured" not in src
    assert "_extract_json_object" not in src
    assert "re.findall" not in src
    assert "re.search" not in src
    assert "json.JSONDecoder" not in src


def test_agent_container_scrape_not_used_for_acp_kind() -> None:
    """run_l1 routes executor:acp to AcpExecutor, not ContainerCLIExecutor scrape."""
    run_l1 = (REPO / "src/bora/application/run_l1.py").read_text(encoding="utf-8")
    assert "AcpExecutor" in run_l1
    assert 'if kind == "acp"' in run_l1 or "kind == 'acp'" in run_l1


def test_agent_acp_imports_typed_sdk() -> None:
    src = (ADAPTERS / "agent_acp.py").read_text(encoding="utf-8")
    assert "agent-client-protocol" in src or "import acp" in src or "from acp" in src
    tree = ast.parse(src)
    assert any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in tree.body)


def test_private_executor_factories_are_tombstones() -> None:
    """Spec 19 Phase 5: private kinds must not construct working parsers."""
    from bora.adapters.agent_registry import resolve_executor

    for kind, entry in (
        ("codex", "codex"),
        ("pi", "pi"),
        ("opencode", "opencode"),
        ("claude-code", "claude-code"),
    ):
        try:
            resolve_executor(kind, model="x")
            raise AssertionError(f"{kind} factory must raise KeyError migration tombstone")
        except KeyError as exc:
            msg = str(exc)
            assert "migrated" in msg.lower() or "acp" in msg.lower()
            assert entry in msg


def test_docker_image_does_not_install_python_acp_sdk() -> None:
    install = (REPO / "docker/attempt/install-executors.sh").read_text(encoding="utf-8")
    assert "agent-client-protocol" not in install
    assert "pip install" not in install
