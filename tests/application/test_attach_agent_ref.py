"""Delayed published agent_ref attach compares harness identity, not model."""

from __future__ import annotations

import pytest

from ageval.application.suite.attach_agent_ref import (
    AttachAgentRefError,
    format_published_agent_ref,
    inject_published_agent_ref,
    parse_published_agent_spec,
    strip_published_agent_ref,
)
from ageval.application.suite.suite_config_fingerprint import fingerprint_for_job_overlay

GROK = {
    "executor": "acp",
    "extensions": [{"plugin": "acp", "options": {"entry": "grok-build"}}],
    "model": "g1",
    "api_key": "OPENAI_API_KEY",
}


def test_parse_published_spec_and_reject_local_file() -> None:
    assert parse_published_agent_spec("acme/http-default@0.1.0") == (
        None,
        "acme/http-default",
        "0.1.0",
    )
    assert parse_published_agent_spec("solver=acme/http-default@0.1.0+sha256:aaaaaaaaaaaa") == (
        "solver",
        "acme/http-default",
        "0.1.0",
    )
    with pytest.raises(AttachAgentRefError, match="published"):
        parse_published_agent_spec("local/http-default@0.1.0")
    with pytest.raises(AttachAgentRefError, match="published"):
        parse_published_agent_spec("file:/tmp/agent@dev")
    with pytest.raises(AttachAgentRefError, match="builtin harness id"):
        parse_published_agent_spec("acme/http-default")
    assert parse_published_agent_spec("pi") == (None, "pi", "0.1.0")
    assert parse_published_agent_spec("solver=opencode")[1:] == ("opencode", "0.1.0")
    assert parse_published_agent_spec("pi@0.1.0") == (None, "pi", "0.1.0")
    assert parse_published_agent_spec("service=openai-http")[0] == "service"


def test_inject_matches_all_roles_and_keeps_fingerprint() -> None:
    overlay = {
        "agent_profiles": {
            "solver": dict(GROK),
            "user": {**GROK, "model": "other"},
        }
    }
    ref = format_published_agent_ref("acme/http-default", "0.1.0", "sha256:" + "a" * 64)
    before = fingerprint_for_job_overlay(overlay)
    result = inject_published_agent_ref(overlay, published_binding=GROK, agent_ref=ref)
    assert result.roles == ("solver", "user")
    assert result.changed is True
    assert result.overlay["agent_profiles"]["solver"]["agent_ref"] == ref
    assert result.overlay["agent_profiles"]["user"]["agent_ref"] == ref
    assert fingerprint_for_job_overlay(result.overlay) == before
    assert before != fingerprint_for_job_overlay(
        {"agent_profiles": {"solver": dict(GROK), "user": dict(GROK)}}
    )


def test_inject_named_role_mismatch_writes_nothing() -> None:
    overlay = {"agent_profiles": {"solver": dict(GROK)}}
    ref = "acme/http-default@0.1.0"
    mismatch = {
        **GROK,
        "extensions": [{"plugin": "acp", "options": {"entry": "codex"}}],
    }
    with pytest.raises(AttachAgentRefError, match="does not match"):
        inject_published_agent_ref(
            overlay,
            published_binding=mismatch,
            agent_ref=ref,
            role="solver",
        )
    assert "agent_ref" not in overlay["agent_profiles"]["solver"]


def test_inject_conflict_and_idempotent_same_ref() -> None:
    overlay = {
        "agent_profiles": {
            "solver": {**GROK, "agent_ref": "acme/http-default@0.1.0+sha256:aaaaaaaaaaaa"},
        }
    }
    same = inject_published_agent_ref(
        overlay,
        published_binding=GROK,
        agent_ref="acme/http-default@0.1.0+sha256:aaaaaaaaaaaa",
    )
    assert same.changed is False
    assert same.roles == ("solver",)
    with pytest.raises(AttachAgentRefError, match="different agent_ref"):
        inject_published_agent_ref(
            overlay,
            published_binding=GROK,
            agent_ref="acme/other@0.1.0+sha256:bbbbbbbbbbbb",
        )


def test_inject_ignores_plugin_options_fingerprint_still_sees_them() -> None:
    with_effort = {
        **GROK,
        "extensions": [
            {"plugin": "acp", "options": {"entry": "grok-build", "reasoning_effort": "max"}}
        ],
    }
    overlay = {"agent_profiles": {"solver": dict(with_effort)}}
    bare = {"agent_profiles": {"solver": dict(GROK)}}
    before = fingerprint_for_job_overlay(overlay)
    assert before != fingerprint_for_job_overlay(bare)
    result = inject_published_agent_ref(
        overlay,
        published_binding=GROK,
        agent_ref="acme/http-default@0.1.0",
    )
    assert result.roles == ("solver",)
    assert fingerprint_for_job_overlay(result.overlay) == before


def test_inject_openai_http_ignores_model_and_effort() -> None:
    published = {
        "executor": "openai-http",
        "extensions": [{"plugin": "openai-http"}, {"plugin": "local"}],
    }
    overlay = {
        "agent_profiles": {
            "user": {
                **published,
                "model": "dashscope/qwen3.8-max",
                "options": {"reasoning_effort": "max"},
            },
            "service": {
                **published,
                "model": "dashscope/deepseek-v4-pro",
                "options": {"reasoning_effort": "max"},
            },
        }
    }
    result = inject_published_agent_ref(
        overlay,
        published_binding=published,
        agent_ref="openai-http@0.1.0",
    )
    assert result.roles == ("user", "service")
    named = inject_published_agent_ref(
        overlay,
        published_binding=published,
        agent_ref="openai-http@0.1.0",
        role="service",
    )
    assert named.roles == ("service",)
    assert "agent_ref" not in named.overlay["agent_profiles"]["user"]
    assert named.overlay["agent_profiles"]["service"]["agent_ref"] == "openai-http@0.1.0"


def test_inject_ignores_locators_environment_overlays() -> None:
    suite = {
        "agent_profiles": {
            "solver": {
                **GROK,
                "base_url": "OPENAI_BASE_URL",
                "overlays": ["overlays/skills/demo"],
            }
        },
        "environment": "docker",
    }
    published = {**GROK, "base_url": "OTHER_BASE", "overlays": ["overlays/other"]}
    result = inject_published_agent_ref(
        suite,
        published_binding=published,
        agent_ref="acme/http-default@0.1.0",
    )
    assert result.roles == ("solver",)
    assert result.overlay["environment"] == "docker"
    assert result.overlay["agent_profiles"]["solver"]["overlays"] == ["overlays/skills/demo"]


def test_strip_named_role_leaves_teammate() -> None:
    overlay = {
        "agent_profiles": {
            "user": {**GROK, "agent_ref": "openai-http@0.1.0"},
            "service": {**GROK, "agent_ref": "openai-http@0.1.0"},
        }
    }
    result = strip_published_agent_ref(overlay, package_id="openai-http", role="service")
    assert result.changed is True
    assert "agent_ref" not in result.overlay["agent_profiles"]["service"]
    assert result.overlay["agent_profiles"]["user"]["agent_ref"] == "openai-http@0.1.0"
