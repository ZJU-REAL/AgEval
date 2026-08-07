"""Focused AcpExecutor unit tests (fixture-free mapping + offline + #30 usage)."""

from __future__ import annotations

import os

from bora.adapters.acp import AcpExecutor, normalize_acp_usage
from bora.adapters.agent_contract import parse_validated_text_structured


def test_validated_text_structured_policy() -> None:
    assert parse_validated_text_structured('{"answer": 42}') == {"answer": 42}
    # Prose around JSON → no salvage
    assert parse_validated_text_structured('Here is {"answer": 42} done') is None
    assert parse_validated_text_structured("[1,2,3]") is None
    assert parse_validated_text_structured("") is None


def test_offline_forced() -> None:
    os.environ["BORA_OFFLINE_AGENT"] = "1"
    try:
        ex = AcpExecutor(entry_id="opencode", model="entry-default")
        r = ex.invoke("hi", timeout=5)
        assert r.ok is False
        assert r.error == "offline_forced"
        assert r.metadata is not None
        assert r.metadata.get("executor_kind") == "acp"
    finally:
        os.environ.pop("BORA_OFFLINE_AGENT", None)


def test_unknown_entry_raises() -> None:
    try:
        AcpExecutor(entry_id="not-an-entry", model="x")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_normalize_acp_usage_dual_source_merge() -> None:
    """PromptResponse tokens + UsageUpdate context/cost merge without used→tokens."""
    out = normalize_acp_usage(
        prompt_usage={
            "inputTokens": 11433,
            "outputTokens": 140,
            "totalTokens": 11573,
            "thoughtTokens": 124,
            "cachedReadTokens": 8576,
            "cachedWriteTokens": 0,
        },
        usage_update={
            "used": 15925,
            "size": 1_000_000,
            "cost": {"amount": 0.012, "currency": "USD"},
            "sessionUpdate": "usage_update",
        },
    )
    assert out is not None
    assert out["input_tokens"] == 11433
    assert out["output_tokens"] == 140
    assert out["total_tokens"] == 11573
    assert out["thought_tokens"] == 124
    assert out["cached_read_tokens"] == 8576
    assert out["cached_write_tokens"] == 0
    assert out["context"] == {"used": 15925, "size": 1_000_000}
    assert out["cost"] == {"amount": 0.012, "currency": "USD"}
    assert out["sources"] == {"prompt_usage": True, "usage_update": True}
    # Never invent uncached_* or promote used as tokens.
    assert "uncached_input_tokens" not in out
    assert "used" not in out
    assert out.get("input_tokens") != out["context"]["used"]


def test_normalize_acp_usage_only_usage_update() -> None:
    out = normalize_acp_usage(
        prompt_usage=None,
        usage_update={"used": 100, "size": 1000, "cost": {"amount": 0.0, "currency": "USD"}},
    )
    assert out is not None
    assert "input_tokens" not in out
    assert "output_tokens" not in out
    assert out["context"] == {"used": 100, "size": 1000}
    assert out["cost"]["currency"] == "USD"
    assert out["sources"] == {"prompt_usage": False, "usage_update": True}


def test_normalize_acp_usage_only_prompt_usage_snake() -> None:
    out = normalize_acp_usage(
        prompt_usage={
            "input_tokens": 10,
            "output_tokens": 2,
            "cached_read_tokens": 8,
        },
        usage_update=None,
    )
    assert out is not None
    assert out["input_tokens"] == 10
    assert out["output_tokens"] == 2
    assert out["total_tokens"] == 12  # derived
    assert out["cached_read_tokens"] == 8
    assert "context" not in out
    assert out["sources"]["prompt_usage"] is True
    assert out["sources"]["usage_update"] is False
    # Cache hit rate is consumer-side: cached_read / input when input > 0.
    assert out["cached_read_tokens"] / out["input_tokens"] == 0.8


def test_normalize_acp_usage_empty() -> None:
    assert normalize_acp_usage(None, None) is None
    assert normalize_acp_usage({}, {}) is None
