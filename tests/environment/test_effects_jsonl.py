"""Environment Manager records allow/deny decisions in effects.jsonl."""

from __future__ import annotations

from pathlib import Path

from ageval.environment.manager import EnvironmentManager
from ageval.evidence.store import AttemptEvidenceStore, parse_jsonl_recover


def test_deny_unknown_kind_writes_effect(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "e", attempt_id="a")
    mgr = EnvironmentManager(attempt_id="a", evidence_store=store)
    r = mgr.open_resource("not-a-resource")
    assert r["ok"] is False
    effects = parse_jsonl_recover(store.root / "effects.jsonl")
    assert any(e.get("decision") == "deny" for e in effects)


def test_action_limit_deny_zero_mutation_path(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(root=tmp_path / "e", attempt_id="a")
    mgr = EnvironmentManager(attempt_id="a", action_limit=0, evidence_store=store)
    # No resource opened — action limit checked first only after resource; open blocked by limit?
    # action_limit 0 means first action fails
    mgr._resources["postgresql:fake"] = object()  # type: ignore[assignment]
    r = mgr.action("postgresql:fake", "execute", {"sql": "SELECT 1"})
    assert r["ok"] is False
    assert r["error"] == "environment_action_limit_exceeded"
    effects = parse_jsonl_recover(store.root / "effects.jsonl")
    assert any(e.get("reason") == "environment_action_limit_exceeded" for e in effects)
