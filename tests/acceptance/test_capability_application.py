"""Capability application checkpoint acceptance."""

from __future__ import annotations

from pathlib import Path

import pytest

from bora.adapters.package_fs import LocalPackageReader
from bora.application.run_capability_probe import run_capability_probe
from bora.capabilities.errors import CapabilityError
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.load_and_lock import ConfigCore

REPO = Path(__file__).resolve().parents[2]
MINIMAL = REPO / "examples" / "core" / "tasks" / "config-minimal"


def _lock():
    return ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        MINIMAL, "config-minimal", capabilities=DeclarationCapabilityCatalog()
    )


@pytest.mark.asyncio
async def test_success_capability_bundle() -> None:
    lock = _lock()
    auth = await run_capability_probe(lock)
    view = auth.parameter_view()
    assert "seed" in view
    d = await auth.publish_artifact("result", b'{"ok":true}')
    assert d.allowed
    e = await auth.emit_event("progress", {"n": 1})
    assert e.allowed
    auth.close()
    with pytest.raises(CapabilityError):
        auth.parameter_view()


@pytest.mark.asyncio
async def test_undeclared_artifact() -> None:
    auth = await run_capability_probe(_lock())
    d = await auth.publish_artifact("missing", b"x")
    assert not d.allowed


@pytest.mark.asyncio
async def test_undeclared_environment_action() -> None:
    auth = await run_capability_probe(_lock(), declared_environment_actions=frozenset())
    d = await auth.authorize_environment_action("nope")
    assert not d.allowed


@pytest.mark.asyncio
async def test_closed() -> None:
    auth = await run_capability_probe(_lock())
    auth.close()
    with pytest.raises(CapabilityError) as ei:
        await auth.emit_event("x")
    assert ei.value.error_code == "closed"


@pytest.mark.asyncio
async def test_hard_ceiling() -> None:
    auth = await run_capability_probe(_lock(), agent_invocation_limit=1)
    started = {"n": 0}

    async def sink() -> None:
        started["n"] += 1

    assert (await auth.run_agent_with_test_sink("p", sink)).allowed
    assert not (await auth.run_agent_with_test_sink("p", sink)).allowed
    assert started["n"] == 1
