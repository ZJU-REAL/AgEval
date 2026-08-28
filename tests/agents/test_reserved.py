"""Builtin harness catalog ids are overlay routes, not org/name leaves."""

from __future__ import annotations

import pytest

from ageval.agents.reserved import (
    builtin_harness_ids,
    builtin_harness_root,
    canonical_harness_id,
    reject_reserved_harness_id,
    reserved_harness_leaf,
)
from ageval.config.errors import ConfigError


def test_catalog_short_ids() -> None:
    ids = builtin_harness_ids()
    assert ids >= frozenset(
        {"pi", "opencode", "codex", "claude-code", "grok-build", "openai-http", "anthropic-http"}
    )
    assert "acp" not in ids
    assert "docker" not in ids


def test_canonical_harness_id_is_short_only() -> None:
    assert canonical_harness_id("pi") == "pi"
    assert canonical_harness_id("PI") == "pi"
    assert canonical_harness_id("pi@0.1.0") == "pi"
    assert canonical_harness_id("official/pi") is None
    assert canonical_harness_id("official/openai-http") is None
    assert canonical_harness_id("official/pi-default") is None


def test_reserved_leaf_catches_org_prefix() -> None:
    assert reserved_harness_leaf("openai-http") == "openai-http"
    assert reserved_harness_leaf("official/openai-http") == "openai-http"
    assert reserved_harness_leaf("official/pi-default") is None
    with pytest.raises(ConfigError, match="ships with ageval"):
        reject_reserved_harness_id("pi")
    with pytest.raises(ConfigError, match="ships with ageval"):
        reject_reserved_harness_id("acme/OpenAI-HTTP")


def test_builtin_tree_has_agent_yaml() -> None:
    root = builtin_harness_root("opencode")
    assert (root / "agent.yaml").is_file()
    assert (root / "overlays" / "opencode.litellm.json").is_file()
    pi = builtin_harness_root("pi")
    assert (pi / "agent.yaml").is_file()
    assert not (pi / "overlays").exists()
