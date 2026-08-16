"""Harness plaza identity is executor + secret-free options only."""

from __future__ import annotations

from bora.config.runtime_identity import (
    appearance_entry,
    harness_display_name,
    harness_fingerprint,
    project_harness,
)

GROK_BUILD = {
    "executor": "acp",
    "options": {"entry": "grok-build"},
    "model": "g1",
}

# Locked vector: rt_ + sha256(canonical project_harness)[:16]
GROK_BUILD_ID = "rt_7bd3fd723961259d"


def test_stable_fingerprint_vector() -> None:
    assert harness_fingerprint(GROK_BUILD) == GROK_BUILD_ID
    assert (
        harness_fingerprint(
            {
                "executor": "acp",
                "options": {"entry": "grok-build"},
                "model": "other-model",
                "label": "ignored",
            }
        )
        == GROK_BUILD_ID
    )


def test_options_key_order_and_denylist_do_not_change_id() -> None:
    a = {
        "executor": "acp",
        "options": {"entry": "grok-build", "mode": "fast", "command": "/bin/secret"},
    }
    b = {
        "executor": "acp",
        "options": {"mode": "fast", "entry": "grok-build", "_acp_lock": "x"},
    }
    assert project_harness(a)["options"] == {"entry": "grok-build", "mode": "fast"}
    assert harness_fingerprint(a) == harness_fingerprint(b)


def test_model_secrets_label_team_excluded() -> None:
    harness = project_harness(
        {
            "id": "service",
            "executor": "nooa",
            "model": "openai/glm-5.2",
            "api_key": "OPENAI_API_KEY",
            "base_url": "https://example.invalid",
            "label": "Prod Nooa",
            "team": {"enabled": True},
            "options": {"agent": "nooa"},
        }
    )
    assert harness == {"executor": "nooa", "options": {"agent": "nooa"}}
    assert set(harness) == {"executor", "options"}


def test_same_nooa_bindings_share_id() -> None:
    service = {"executor": "nooa", "options": {"agent": "nooa"}, "model": "m1"}
    user = {"executor": "nooa", "options": {"agent": "nooa"}, "model": "m1"}
    assert harness_fingerprint(service) == harness_fingerprint(user)


def test_different_plugin_options_differ() -> None:
    a = {"executor": "dsh", "options": {"permission": "default"}}
    b = {"executor": "dsh", "options": {"permission": "read-only"}}
    assert harness_fingerprint(a) != harness_fingerprint(b)


def test_display_name_humanizes_entry() -> None:
    assert harness_display_name(GROK_BUILD) == "Grok Build"
    assert harness_display_name({"executor": "nooa"}) == "Nooa"
    assert harness_display_name({}) == "Runtime"


def test_appearance_entry_prefers_options() -> None:
    assert appearance_entry(GROK_BUILD) == "grok-build"
    assert appearance_entry({"executor": "nooa", "options": {"agent": "nooa"}}) == "nooa"
    assert appearance_entry({"executor": "dsh"}) == "dsh"
