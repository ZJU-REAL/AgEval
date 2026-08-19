"""Plaza identity is the agent product, not transport ``acp``."""

from __future__ import annotations

from ageval.config.runtime_identity import (
    agent_display_name,
    agent_fingerprint,
    profile_options,
    project_agent_identity,
    resolve_agent_id,
)

GROK_BUILD = {
    "executor": "acp",
    "extensions": [{"plugin": "acp", "options": {"entry": "grok-build"}}],
    "model": "g1",
}

# Locked vector: rt_ + sha256({"agent":"grok-build"})[:16]
GROK_BUILD_ID = "rt_fe4e354ca9b35abc"


def _acp(entry: str, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "executor": "acp",
        "extensions": [{"plugin": "acp", "options": {"entry": entry}}],
    }
    row.update(extra)
    return row


def test_stable_fingerprint_vector() -> None:
    assert resolve_agent_id(GROK_BUILD) == "grok-build"
    assert project_agent_identity(GROK_BUILD) == {"agent": "grok-build"}
    assert agent_fingerprint(GROK_BUILD) == GROK_BUILD_ID
    assert (
        agent_fingerprint(_acp("grok-build", model="other-model", label="ignored")) == GROK_BUILD_ID
    )
    with_overlays = dict(GROK_BUILD)
    with_overlays["overlays"] = ["overlays/skills/jsonl-agg", "overlays/AGENTS.md"]
    assert agent_fingerprint(with_overlays) == GROK_BUILD_ID


def test_extension_row_with_home_files_still_resolves() -> None:
    overlay_binding = {
        "executor": "acp",
        "api_key": "litellm_api_key",
        "base_url": "http://example.invalid/v1",
        "model": "litellm/dashscope/qwen3.8-max",
        "extensions": [
            {"plugin": "acp", "options": {"entry": "opencode"}},
            {
                "plugin": "home-files",
                "options": {"files": [{"src": "overlays/opencode.litellm.json"}]},
            },
        ],
    }
    assert resolve_agent_id(overlay_binding) == "opencode"
    assert agent_display_name(overlay_binding) == "Opencode"
    assert profile_options(overlay_binding) == {"entry": "opencode"}


def test_profile_options_entry_is_not_identity() -> None:
    stale = {"executor": "acp", "options": {"entry": "grok-build"}}
    assert resolve_agent_id(stale) == ""
    assert agent_fingerprint(stale) == ""


def test_acp_entries_are_distinct_agents() -> None:
    assert agent_fingerprint(_acp("pi")) != agent_fingerprint(_acp("opencode"))
    assert agent_fingerprint(_acp("pi")) != GROK_BUILD_ID


def test_bare_acp_is_not_an_agent() -> None:
    assert resolve_agent_id({"executor": "acp"}) == ""
    assert agent_fingerprint({"executor": "acp"}) == ""
    assert agent_display_name({"executor": "acp"}) == "Runtime"


def test_model_secrets_label_team_excluded() -> None:
    harness = project_agent_identity(
        {
            "id": "service",
            "executor": "nooa",
            "model": "openai/glm-5.2",
            "api_key": "OPENAI_API_KEY",
            "base_url": "https://example.invalid",
            "label": "Prod Nooa",
            "team": {"enabled": True},
            "extensions": [{"plugin": "nooa", "options": {"agent": "lib.agents:JsonlAggAgent"}}],
        }
    )
    assert harness == {"agent": "nooa"}


def test_same_nooa_bindings_share_id() -> None:
    service = {
        "executor": "nooa",
        "extensions": [{"plugin": "nooa", "options": {"agent": "nooa"}}],
        "model": "m1",
    }
    user = {
        "executor": "nooa",
        "extensions": [{"plugin": "nooa", "options": {"agent": "nooa"}}],
        "model": "m1",
    }
    assert agent_fingerprint(service) == agent_fingerprint(user)


def test_plugin_knobs_do_not_split_agent() -> None:
    a = {
        "executor": "dsh",
        "extensions": [{"plugin": "dsh", "options": {"permission": "default"}}],
    }
    b = {
        "executor": "dsh",
        "extensions": [{"plugin": "dsh", "options": {"permission": "read-only"}}],
    }
    assert agent_fingerprint(a) == agent_fingerprint(b)
    assert project_agent_identity(a) == {"agent": "dsh"}


def test_display_name_follows_hub_agent_axis() -> None:
    assert agent_display_name(_acp("pi", label="pi-agent")) == "pi-agent"
    assert agent_display_name(_acp("pi")) == "Pi"
    assert agent_display_name(_acp("opencode")) == "Opencode"
    assert agent_display_name(GROK_BUILD) == "Grok Build"
    assert agent_display_name({"executor": "dsh"}) == "Dsh"
    assert agent_display_name({"executor": "nooa"}) == "Nooa"
    assert agent_display_name({}) == "Runtime"


def test_resolve_agent_id_is_product() -> None:
    assert resolve_agent_id(_acp("pi")) == "pi"
    assert (
        resolve_agent_id(
            {
                "executor": "nooa",
                "extensions": [{"plugin": "nooa", "options": {"agent": "lib.x"}}],
            }
        )
        == "nooa"
    )
    assert resolve_agent_id({"executor": "dsh"}) == "dsh"
    assert profile_options(GROK_BUILD) == {"entry": "grok-build"}
