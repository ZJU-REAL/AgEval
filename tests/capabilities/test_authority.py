"""Capability authority unit tests."""

from __future__ import annotations

import asyncio

import pytest

from ageval.capabilities.authority import AttemptCapabilityAuthority
from ageval.capabilities.errors import CapabilityError
from ageval.runtime.identity import IdentityFactory


def _auth(**kwargs) -> AttemptCapabilityAuthority:
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, "sha256:" + "c" * 64)
    attempt = f.new_attempt(trial)
    base = {
        "attempt": attempt,
        "params": {"seed": 1},
        "declared_artifacts": frozenset({"result"}),
        "declared_environment_actions": frozenset({"ping"}),
        "agent_invocation_limit": 1,
        "environment_action_limit": 1,
    }
    base.update(kwargs)
    return AttemptCapabilityAuthority(**base)


@pytest.mark.asyncio
async def test_params_and_publish() -> None:
    auth = _auth()
    assert auth.parameter_view()["seed"] == 1
    d = await auth.publish_artifact("result", b"{}")
    assert d.allowed
    d2 = await auth.publish_artifact("nope", b"x")
    assert not d2.allowed
    assert d2.reason == "undeclared"


@pytest.mark.asyncio
async def test_closed() -> None:
    auth = _auth()
    auth.close()
    with pytest.raises(CapabilityError) as ei:
        auth.parameter_view()
    assert ei.value.error_code == "closed"


@pytest.mark.asyncio
async def test_hard_ceiling_last_slot() -> None:
    auth = _auth(agent_invocation_limit=1)
    started = {"n": 0}

    async def sink() -> None:
        started["n"] += 1

    d1 = await auth.run_agent_with_test_sink("p", sink)
    assert d1.allowed
    assert started["n"] == 1
    d2 = await auth.run_agent_with_test_sink("p", sink)
    assert not d2.allowed
    assert d2.reason == "quota_exceeded"
    assert started["n"] == 1
    assert auth.agent_sink_starts == 1


@pytest.mark.asyncio
async def test_concurrent_last_quota() -> None:
    auth = _auth(agent_invocation_limit=1)
    started = {"n": 0}

    async def sink() -> None:
        started["n"] += 1
        await asyncio.sleep(0.01)

    results = await asyncio.gather(
        auth.run_agent_with_test_sink("a", sink),
        auth.run_agent_with_test_sink("b", sink),
    )
    allowed = [r for r in results if r.allowed]
    denied = [r for r in results if not r.allowed]
    assert len(allowed) == 1
    assert len(denied) == 1
    assert started["n"] == 1


@pytest.mark.asyncio
async def test_unavailable_agent() -> None:
    auth = _auth()
    with pytest.raises(CapabilityError) as ei:
        await auth.invoke_agent_unavailable("mock")
    assert ei.value.error_code == "capability_unavailable"
