"""Spec 01/02: ACP first-party + external nooa install binding isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.plugins.bootstrap import bootstrap_registry
from bora.plugins.contrib.acp import PLUGIN_ID as ACP_ID
from bora.plugins.errors import ExtensionMaterializeError
from bora.plugins.lock_bind import extension_graph_to_lock
from bora.plugins.protocol import BindingIntent
from bora.plugins.registry import ExtensionRegistry, reset_global_registry
from bora.plugins.resolve import resolve
from bora.plugins.slots import EXECUTOR
from bora.runtime.parent_agent_service import ParentAgentService

ROOT = Path(__file__).resolve().parents[2]
NOOA_PKG = ROOT / "plugins" / "nooa"
NOOA_ID = "nooa"


@pytest.fixture()
def bora_home_with_nooa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "bora-home"
    home.mkdir()
    monkeypatch.setenv("BORA_HOME", str(home))
    from bora.plugins import bootstrap as boot
    from bora.plugins.store import install_from_path

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    assert NOOA_PKG.is_dir()
    install_from_path(NOOA_PKG)
    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    return home


def test_acp_provide_selected_by_profile_executor() -> None:
    reg = ExtensionRegistry()
    bootstrap_registry(reg, include_mock=False, include_openai_http=False)
    graph = resolve(
        BindingIntent(profile_id="solver", executor="acp", options={"entry": "pi"}),
        reg,
        materialize=False,
    )
    assert graph.providers[EXECUTOR].plugin_id == ACP_ID
    lock = extension_graph_to_lock(graph)
    assert lock["executor"]["plugin"] == "acp"
    assert lock["executor"]["source"] == "profile_executor_field"


def test_bootstrap_default_has_no_nooa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """nooa is ecosystem-only — not first-party bootstrap (isolated cache)."""
    home = tmp_path / "bora-home-empty"
    home.mkdir()
    monkeypatch.setenv("BORA_HOME", str(home))
    from bora.plugins import bootstrap as boot

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    reg = ExtensionRegistry()
    bootstrap_registry(reg, include_mock=False, include_openai_http=False)
    assert NOOA_ID not in reg.plugins_for_slot(EXECUTOR)


def test_nooa_require_options_agent(bora_home_with_nooa: Path) -> None:
    del bora_home_with_nooa
    reg = ExtensionRegistry()
    bootstrap_registry(reg, include_mock=False, include_openai_http=False)
    with pytest.raises(ExtensionMaterializeError) as ei:
        resolve(
            BindingIntent(profile_id="s", executor="nooa", options={}),
            reg,
            materialize=True,
        )
    assert "nooa_options_agent_required" in str(ei.value)


def test_nooa_installed_resolve(bora_home_with_nooa: Path) -> None:
    del bora_home_with_nooa
    reg = ExtensionRegistry()
    bootstrap_registry(reg, include_mock=False, include_openai_http=False)
    assert NOOA_ID in reg.plugins_for_slot(EXECUTOR)
    graph = resolve(
        BindingIntent(
            profile_id="solver",
            executor="nooa",
            options={"agent": "types:SimpleNamespace", "method": "__str__"},
        ),
        reg,
        materialize=False,
    )
    assert graph.providers[EXECUTOR].plugin_id == NOOA_ID
    lock = extension_graph_to_lock(graph)
    assert lock["executor"]["plugin"] == "nooa"
    assert lock["executor"]["source"] == "profile_executor_field"


def test_dual_profile_acp_and_nooa_session_graphs(bora_home_with_nooa: Path) -> None:
    del bora_home_with_nooa
    reg = ExtensionRegistry()
    bootstrap_registry(reg, include_mock=False, include_openai_http=False)
    svc = ParentAgentService(
        profiles=[
            {
                "id": "solver",
                "executor": "nooa",
                "model": "m",
                "options": {"agent": "types:SimpleNamespace", "method": "__str__"},
            },
            {
                "id": "user",
                "executor": "acp",
                "model": "m",
                "options": {"entry": "pi"},
            },
        ],
        agent_invocation_limit=2,
        attempt_id="attempt_dual",
        offline_env="",
        extension_registry=reg,
    )
    s_solver = svc.open_session(profile_id="solver")
    s_user = svc.open_session(profile_id="user")
    assert s_solver["ok"] is True
    assert s_user["ok"] is True
    assert s_solver["executor_plugin"] == NOOA_ID
    assert s_user["executor_plugin"] == ACP_ID
    g_solver = svc.get_session_extension_graph(s_solver["session_id"])
    g_user = svc.get_session_extension_graph(s_user["session_id"])
    assert g_solver is not None and g_user is not None
    assert g_solver.providers[EXECUTOR].plugin_id == NOOA_ID
    assert g_user.providers[EXECUTOR].plugin_id == ACP_ID
    assert g_solver.providers[EXECUTOR].impl is not g_user.providers[EXECUTOR].impl


def test_nooa_uninstalled_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setenv("BORA_HOME", str(home))
    from bora.plugins import bootstrap as boot
    from bora.plugins.errors import ExtensionPluginNotFoundError

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    reg = ExtensionRegistry()
    bootstrap_registry(reg, include_mock=False, include_openai_http=False)
    with pytest.raises(ExtensionPluginNotFoundError):
        resolve(
            BindingIntent(profile_id="s", executor="nooa", options={"agent": "x:Y"}),
            reg,
            materialize=False,
        )


def test_acp_entry_missing_fail_closed() -> None:
    reg = ExtensionRegistry()
    bootstrap_registry(reg, include_mock=False, include_openai_http=False)
    svc = ParentAgentService(
        profiles=[{"id": "p", "executor": "acp", "model": "m", "options": {}}],
        agent_invocation_limit=1,
        attempt_id="a",
        offline_env="",
        extension_registry=reg,
    )
    opened = svc.open_session(profile_id="p")
    assert opened["ok"] is False
    assert opened["error"] in {"acp_entry_required", "extension_materialize_failed"}
