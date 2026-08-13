"""Shared AgentInvocationQuota ledger."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from bora.capabilities.authority import AttemptCapabilityAuthority
from bora.capabilities.quota import AgentInvocationQuota
from bora.runtime.identity import IdentityFactory


def test_quota_try_consume_exhausts() -> None:
    q = AgentInvocationQuota(limit=2)
    assert q.try_consume() is True
    assert q.remaining == 1
    assert q.try_consume() is True
    assert q.remaining == 0
    assert q.try_consume() is False


def test_authority_consumes_shared_quota() -> None:
    q = AgentInvocationQuota(limit=1)
    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "c" * 64)
    attempt = factory.new_attempt(trial)
    auth = AttemptCapabilityAuthority(
        attempt=attempt,
        params={},
        agent_invocation_limit=1,
        invoke_quota=q,
    )
    decision = asyncio.run(auth.authorize_agent_invoke("p"))
    assert decision.allowed is True
    assert q.remaining == 0
    denied = asyncio.run(auth.authorize_agent_invoke("p"))
    assert denied.allowed is False


def test_parent_service_uses_shared_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    from bora.plugins.bootstrap import ensure_bootstrapped
    from bora.runtime.parent_agent_service import ParentAgentService

    monkeypatch.delenv("BORA_OFFLINE_AGENT", raising=False)
    q = AgentInvocationQuota(limit=1)
    svc = ParentAgentService(
        profiles=[{"id": "p", "executor": "mock", "model": "m"}],
        agent_invocation_limit=1,
        attempt_id="att-1",
        offline_env="",
        extension_registry=ensure_bootstrapped(),
        invoke_quota=q,
    )
    assert q.try_consume() is True  # external authority took the slot
    opened = svc.open_session(profile_id="p")
    assert opened.get("ok") is True
    out = svc.invoke(session_id=opened["session_id"], prompt="hi")
    assert out.get("ok") is False
    assert out.get("error") == "agent_invocation_limit"
    assert os.environ.get("BORA_OFFLINE_AGENT") != "1"


def test_assemble_parent_and_authority_share_quota(tmp_path: Path) -> None:
    from bora.application.attempt.agent_service_assemble import assemble_parent_agent_service

    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "d" * 64)
    attempt = factory.new_attempt(trial)
    service, _timeout, authority = assemble_parent_agent_service(
        profiles=[{"id": "p", "executor": "mock", "model": "m"}],
        package_root=tmp_path,
        attempt=attempt,
        inv_limit=2,
        params={},
        evidence_store=None,
        deadline_monotonic=None,
    )
    assert service.invoke_quota is authority.invoke_quota
