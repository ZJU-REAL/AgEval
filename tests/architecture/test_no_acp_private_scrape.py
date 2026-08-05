"""Architecture gate: one ACP client; private vendor modules deleted."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTERS = REPO / "src" / "bora" / "adapters"


def test_single_acp_executor_module() -> None:
    acp_modules = list(ADAPTERS.glob("agent_acp*.py"))
    assert acp_modules == [ADAPTERS / "agent_acp.py"]


def test_private_vendor_modules_deleted() -> None:
    for name in (
        "agent_codex.py",
        "agent_pi.py",
        "agent_opencode.py",
        "agent_claude_code.py",
    ):
        assert not (ADAPTERS / name).is_file(), f"{name} must be deleted"


def test_acp_module_has_no_regex_json_scrape() -> None:
    src = (ADAPTERS / "agent_acp.py").read_text(encoding="utf-8")
    assert "_try_parse_structured" not in src
    assert "_extract_json_object" not in src
    assert "re.findall" not in src
    assert "re.search" not in src


def test_container_module_has_no_vendor_scrape() -> None:
    src = (ADAPTERS / "agent_container.py").read_text(encoding="utf-8")
    assert "_try_parse_structured" not in src
    assert "_extract_json_object" not in src
    assert "_cli_argv" not in src
    assert "re.search" not in src
    assert "new_opaque_target_id" in src


def test_agent_container_scrape_not_used_for_acp_kind() -> None:
    run_l1 = (REPO / "src/bora/application/run_l1.py").read_text(encoding="utf-8")
    assert "AcpExecutor" in run_l1
    assert "migrated_to_acp" in run_l1


def test_agent_acp_imports_typed_sdk() -> None:
    src = (ADAPTERS / "agent_acp.py").read_text(encoding="utf-8")
    assert "import acp" in src or "from acp" in src
    tree = ast.parse(src)
    assert any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in tree.body)


def test_private_kinds_not_resolvable() -> None:
    from bora.adapters.agent_registry import resolve_executor

    for kind in ("codex", "pi", "opencode", "claude-code"):
        try:
            resolve_executor(kind, model="x")
            raise AssertionError(f"{kind} must not resolve")
        except KeyError:
            pass


def test_docker_image_does_not_install_python_acp_sdk() -> None:
    install = (REPO / "docker/attempt/install-executors.sh").read_text(encoding="utf-8")
    assert "agent-client-protocol" not in install
    assert "pip install" not in install
