"""Spec 01/02: ACP + nooa first-party contribs and dual-profile isolation."""

from __future__ import annotations

import pytest

from bora.plugins.bootstrap import bootstrap_registry
from bora.plugins.contrib.acp import PLUGIN_ID as ACP_ID
from bora.plugins.contrib.nooa import PLUGIN_ID as NOOA_ID
from bora.plugins.contrib.nooa import NooaExecutorSPI
from bora.plugins.errors import ExtensionMaterializeError
from bora.plugins.lock_bind import extension_graph_to_lock
from bora.plugins.protocol import BindingIntent
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.resolve import resolve
from bora.plugins.slots import EXECUTOR
from bora.runtime.parent_agent_service import ParentAgentService


def test_acp_provide_selected_by_profile_executor() -> None:
    reg = ExtensionRegistry()
    bootstrap_registry(reg, include_nooa=False, include_mock=False, include_openai_http=False)
    graph = resolve(
        BindingIntent(profile_id="solver", executor="acp", options={"entry": "pi"}),
        reg,
        materialize=False,
    )
    assert graph.providers[EXECUTOR].plugin_id == ACP_ID
    lock = extension_graph_to_lock(graph)
    assert lock["executor"]["plugin"] == "acp"
    assert lock["executor"]["source"] == "profile_executor_field"


def test_nooa_require_options_agent() -> None:
    with pytest.raises(ExtensionMaterializeError) as ei:
        NooaExecutorSPI(options={})
    assert "nooa_options_agent_required" in str(ei.value)


def test_dual_profile_acp_and_nooa_session_graphs() -> None:
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
    # Instances must not be shared across sessions
    assert g_solver.providers[EXECUTOR].impl is not g_user.providers[EXECUTOR].impl


def test_acp_entry_missing_fail_closed() -> None:
    reg = ExtensionRegistry()
    bootstrap_registry(reg, include_nooa=False, include_mock=False, include_openai_http=False)
    svc = ParentAgentService(
        profiles=[{"id": "p", "executor": "acp", "model": "m", "options": {}}],
        agent_invocation_limit=1,
        attempt_id="a",
        extension_registry=reg,
    )
    opened = svc.open_session(profile_id="p")
    assert opened["ok"] is False
    assert opened["error"] == "acp_entry_required"
