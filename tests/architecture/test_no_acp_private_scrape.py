"""Architecture gate: one ACP client package; private vendor modules deleted."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTERS = REPO / "src" / "bora" / "adapters"
ACP_PKG = ADAPTERS / "acp"


def _acp_sources() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(ACP_PKG.glob("*.py")))


def test_single_acp_executor_package() -> None:
    assert ACP_PKG.is_dir()
    assert (ACP_PKG / "executor.py").is_file()
    # No legacy monolith next to the package.
    assert not (ADAPTERS / "agent_acp.py").is_file()
    # No extra top-level agent_acp* modules.
    assert list(ADAPTERS.glob("agent_acp*.py")) == []


def test_private_vendor_modules_deleted() -> None:
    for name in (
        "agent_codex.py",
        "agent_pi.py",
        "agent_opencode.py",
        "agent_claude_code.py",
    ):
        assert not (ADAPTERS / name).is_file(), f"{name} must be deleted"


def test_acp_module_has_no_regex_json_scrape() -> None:
    src = _acp_sources()
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
    app = REPO / "src" / "bora" / "application" / "attempt"
    sources = "\n".join(p.read_text(encoding="utf-8") for p in sorted(app.glob("run_l1*.py")))
    assert "make_l1_placement_resolver" in sources
    assert "migrated_to_acp" not in sources
    assert "NooaContainerExecutor" not in sources
    container = (ADAPTERS / "agent_container.py").read_text(encoding="utf-8")
    assert "wrap_docker_exec" in container
    assert "ContainerCLIExecutor" not in container


def test_agent_acp_imports_typed_sdk() -> None:
    src = _acp_sources()
    assert "import acp" in src or "from acp" in src
    # At least one package module parses cleanly with imports present.
    for path in sorted(ACP_PKG.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in tree.body):
            return
    raise AssertionError("ACP package has no import statements")


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
