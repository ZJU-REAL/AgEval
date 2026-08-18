"""Wildcard "*" default binding + agent_ref passthrough in profiles (design/14)."""

from __future__ import annotations

import pytest

from bora.config.errors import ConfigError
from bora.config.profiles import (
    job_overlay_to_profiles_document,
    merge_bindings_onto_slots,
    parse_profiles_mapping,
    project_job_overlay,
)

WILDCARD_DOC = {
    "format": "bora.profiles/1",
    "bindings": {
        "*": {"executor": "mock", "model": "none", "agent_ref": "local/m@0.1.0+sha256:abc"},
        "critic": {"executor": "mock", "model": "other"},
    },
}


def test_parse_accepts_wildcard_key() -> None:
    bindings = parse_profiles_mapping(WILDCARD_DOC)
    assert set(bindings) == {"*", "critic"}


def test_parse_still_rejects_bad_role_ids() -> None:
    doc = {"format": "bora.profiles/1", "bindings": {"**": {"executor": "mock", "model": "x"}}}
    with pytest.raises(ConfigError):
        parse_profiles_mapping(doc)


def test_merge_exact_wins_wildcard_falls_back() -> None:
    bindings = parse_profiles_mapping(WILDCARD_DOC)
    merged = merge_bindings_onto_slots([{"id": "solver"}, {"id": "critic"}], bindings)
    by_id = {row["id"]: row for row in merged}
    assert by_id["solver"]["model"] == "none"  # wildcard fallback
    assert by_id["solver"]["agent_ref"] == "local/m@0.1.0+sha256:abc"
    assert by_id["critic"]["model"] == "other"  # exact wins
    assert "agent_ref" not in by_id["critic"]


def test_merge_without_wildcard_still_fails_closed() -> None:
    bindings = parse_profiles_mapping(
        {"format": "bora.profiles/1", "bindings": {"critic": {"executor": "mock", "model": "x"}}}
    )
    with pytest.raises(ConfigError):
        merge_bindings_onto_slots([{"id": "solver"}], bindings)


def test_project_expands_wildcard_to_real_roles() -> None:
    bindings = parse_profiles_mapping(WILDCARD_DOC)
    overlay = project_job_overlay(bindings, role_ids=["solver", "critic"])
    rows = overlay["bindings"]
    assert set(rows) == {"solver", "critic"}
    assert rows["solver"]["agent_ref"] == "local/m@0.1.0+sha256:abc"
    assert rows["critic"]["model"] == "other"
    assert "*" not in rows


def test_agent_ref_round_trips_via_profiles_document() -> None:
    bindings = parse_profiles_mapping(WILDCARD_DOC)
    overlay = project_job_overlay(bindings, role_ids=["solver"])
    doc = job_overlay_to_profiles_document(overlay)
    assert doc["bindings"]["solver"]["agent_ref"] == "local/m@0.1.0+sha256:abc"


def test_task_yaml_slots_reject_agent_ref_inline() -> None:
    from bora.config.profiles import assert_slots_have_no_inline_binding

    with pytest.raises(ConfigError):
        assert_slots_have_no_inline_binding([{"id": "solver", "agent_ref": "x@1"}])


def test_suite_compat_and_labels_with_wildcard_binding() -> None:
    """Found via live eval: '*' suite binding blanked labels / homogeneity."""
    from bora.application.suite.suite_config_fingerprint import (
        compute_suite_config_fields,
        job_overlays_compatible,
    )

    binding = {
        "executor": "acp",
        "model": "entry-default",
        "label": "Claude Code (entry default)",
        "extensions": [{"plugin": "acp", "options": {"entry": "claude-code"}}],
    }
    suite_overlay = {"bindings": {"*": binding}}
    per_task = [{"bindings": {"solver": dict(binding)}}]

    assert job_overlays_compatible(suite_overlay, per_task) is True
    # A conflicting model for the same role still breaks compatibility.
    conflicting = [{"bindings": {"solver": {**binding, "model": "other"}}}]
    assert job_overlays_compatible(suite_overlay, conflicting) is False

    fields = compute_suite_config_fields([], job_overlay=suite_overlay, per_task_overlays=per_task)
    assert fields["config_homogeneous"] is True
    assert fields["agent_label"] == "Claude Code (entry default)"


def test_wildcard_and_explicit_spellings_share_fingerprint() -> None:
    """Identity must not depend on '*'-vs-explicit spelling (design/14)."""
    from bora.application.suite.suite_config_fingerprint import compute_suite_config_fields

    binding = {
        "executor": "acp",
        "model": "entry-default",
        "extensions": [{"plugin": "acp", "options": {"entry": "claude-code"}}],
    }
    per_task = [{"bindings": {"solver": dict(binding)}}]
    via_wildcard = compute_suite_config_fields(
        [], job_overlay={"bindings": {"*": binding}}, per_task_overlays=per_task
    )
    via_explicit = compute_suite_config_fields(
        [], job_overlay={"bindings": {"solver": dict(binding)}}, per_task_overlays=per_task
    )
    assert via_wildcard["config_fingerprint"] == via_explicit["config_fingerprint"]
    assert [a["profile_id"] for a in via_wildcard["actors_summary"]] == ["solver"]


def test_exact_row_overrides_wildcard_field_wise() -> None:
    """--set on one field of a wildcard-bound agent must not drop the rest."""
    from bora.config.profiles import apply_binding_override, effective_binding

    bindings = parse_profiles_mapping(
        {
            "format": "bora.profiles/1",
            "bindings": {
                "*": {
                    "executor": "acp",
                    "model": "entry-default",
                    "extensions": [{"plugin": "acp", "options": {"entry": "claude-code"}}],
                }
            },
        }
    )
    apply_binding_override(bindings, "/bindings/solver/model", "claude-opus-5")
    merged = merge_bindings_onto_slots([{"id": "solver"}, {"id": "critic"}], bindings)
    by_id = {row["id"]: row for row in merged}
    assert by_id["solver"]["model"] == "claude-opus-5"  # override wins
    assert by_id["solver"]["executor"] == "acp"  # inherited from wildcard
    assert by_id["solver"]["extensions"][0]["options"]["entry"] == "claude-code"
    assert by_id["critic"]["model"] == "entry-default"  # untouched fallback

    eff = effective_binding(bindings, "solver")
    assert eff is not None and eff["model"] == "claude-opus-5" and eff["executor"] == "acp"
