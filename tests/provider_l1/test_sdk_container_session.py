"""Unit: L1 placement resolver fails closed on dead/generation targets."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from bora.adapters.agent_container import effective_run_gid
from bora.application.attempt.run_l1_prepare import make_l1_placement_resolver
from bora.provider.targets import ActorPhysicalBinding, ExecutionTarget


def _binding(**kw: Any) -> ActorPhysicalBinding:
    return ActorPhysicalBinding(
        actor_id=kw.get("actor_id", "a1"),
        group_id=kw.get("group_id", "g1"),
        target_id=kw.get("target_id", "tgt_1"),
        uid=kw.get("uid", 12000),
        gid=kw.get("gid", 12000),
        home_container=kw.get("home_container", "/actor-homes/a1"),
        shared_gid=kw.get("shared_gid"),
        shared_write=kw.get("shared_write", ()),
        generation=kw.get("generation", 1),
    )


def test_target_dead_fail_closed() -> None:
    target = ExecutionTarget(
        target_id="tgt_1",
        group_id="g1",
        generation=1,
        container_id=None,
        state="dead",
    )
    ledger = SimpleNamespace(actors={"a1": _binding()}, targets={"tgt_1": target})
    resolve = make_l1_placement_resolver(ledger=ledger)
    with pytest.raises(RuntimeError, match="target_dead"):
        resolve(SimpleNamespace(actor_id="a1", generation=1, target_id="tgt_1"))


def test_generation_mismatch_fail_closed() -> None:
    target = ExecutionTarget(
        target_id="tgt_1",
        group_id="g1",
        generation=2,
        container_id="cid",
        state="ready",
    )
    ledger = SimpleNamespace(actors={"a1": _binding(generation=1)}, targets={"tgt_1": target})
    resolve = make_l1_placement_resolver(ledger=ledger)
    with pytest.raises(RuntimeError, match="generation_mismatch"):
        resolve(SimpleNamespace(actor_id="a1", generation=1, target_id="tgt_1"))


def test_effective_run_gid_shared_write() -> None:
    actor = _binding(shared_gid=13000, shared_write=("workspace/team",))
    assert effective_run_gid(actor) == 13000
    actor2 = _binding(shared_gid=None, shared_write=())
    assert effective_run_gid(actor2) == 12000
