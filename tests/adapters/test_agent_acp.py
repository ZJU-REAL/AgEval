"""Focused AcpExecutor unit tests (fixture-free mapping + offline + #30 usage)."""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest

from bora.adapters.agent_contract import parse_validated_text_structured
from bora.plugins.contrib.acp import AcpExecutor, normalize_acp_usage
from bora.plugins.contrib.acp.executor import (
    _find_reasoning_config_option,
    _select_option_values,
)


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


def test_ensure_session_requires_workdir() -> None:
    os.environ.pop("BORA_OFFLINE_AGENT", None)
    ex = AcpExecutor(entry_id="opencode", model="entry-default")
    err = ex._ensure_session(workdir=None, timeout=1.0)
    assert err == "acp_workdir_required"


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


def test_find_reasoning_option_prefers_thought_level_category() -> None:
    opts = [
        {"id": "mode", "category": "mode", "options": [{"value": "ask"}]},
        {"id": "effort", "options": [{"value": "high"}]},
        {"id": "thinking", "category": "thought_level", "options": [{"value": "off"}]},
    ]
    found = _find_reasoning_config_option(opts)
    assert found is not None
    assert found["id"] == "thinking"


def test_find_reasoning_option_falls_back_to_known_id() -> None:
    opts = [{"id": "reasoning_effort", "options": [{"value": "high"}]}]
    found = _find_reasoning_config_option(opts)
    assert found is not None
    assert found["id"] == "reasoning_effort"


def test_select_option_values_flattens_groups() -> None:
    opt = {
        "id": "thought_level",
        "options": [
            {"group": "std", "name": "Standard", "options": [{"value": "off"}, {"value": "high"}]},
            {"value": "xhigh"},
        ],
    }
    assert _select_option_values(opt) == ["off", "high", "xhigh"]


class _FakeConn:
    def __init__(self, *, after_model: list[dict[str, object]] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.after_model = after_model

    async def set_config_option(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(dict(kwargs))
        if kwargs.get("config_id") == "model" and self.after_model is not None:
            return SimpleNamespace(config_options=self.after_model)
        return SimpleNamespace(config_options=[])


def _session(*options: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(config_options=list(options))


def _model_opt(*values: str, current: str = "m1") -> dict[str, object]:
    return {
        "id": "model",
        "category": "model",
        "currentValue": current,
        "options": [{"value": v} for v in values],
    }


def _thought_opt(
    *values: str, current: str = "off", option_id: str = "thought_level"
) -> dict[str, object]:
    return {
        "id": option_id,
        "category": "thought_level",
        "currentValue": current,
        "options": [{"value": v} for v in values],
    }


def test_bind_reasoning_effort_after_model() -> None:
    ex = AcpExecutor(entry_id="pi", model="m1", reasoning_effort="high")
    conn = _FakeConn()
    ex._conn = conn
    ex._acp_session_id = "sess"
    asyncio.run(_bind(ex, _session(_model_opt("m1", "m2"), _thought_opt("off", "high"))))
    assert [c["config_id"] for c in conn.calls] == ["model", "thought_level"]
    assert conn.calls[1]["value"] == "high"
    assert ex._actual_reasoning_effort == "high"


def test_bind_reasoning_uses_options_refreshed_after_model() -> None:
    after = [_model_opt("m1"), _thought_opt("off", "xhigh", current="off")]
    ex = AcpExecutor(entry_id="pi", model="m1", reasoning_effort="high")
    conn = _FakeConn(after_model=after)
    ex._conn = conn
    ex._acp_session_id = "sess"
    # session/new advertised ``high``; after model switch only ``xhigh`` remains.
    with pytest.raises(RuntimeError, match="acp_reasoning_effort_unavailable"):
        asyncio.run(_bind(ex, _session(_model_opt("m1"), _thought_opt("off", "high"))))


def test_bind_reasoning_skips_when_already_current() -> None:
    ex = AcpExecutor(entry_id="pi", model="entry-default", reasoning_effort="high")
    conn = _FakeConn()
    ex._conn = conn
    ex._acp_session_id = "sess"
    asyncio.run(
        _bind(
            ex,
            _session(_model_opt("m1", current="m1"), _thought_opt("off", "high", current="high")),
        )
    )
    assert conn.calls == []
    assert ex._actual_reasoning_effort == "high"


def test_bind_reasoning_missing_option_fails() -> None:
    ex = AcpExecutor(entry_id="pi", model="entry-default", reasoning_effort="high")
    conn = _FakeConn()
    ex._conn = conn
    ex._acp_session_id = "sess"
    with pytest.raises(RuntimeError, match="acp_reasoning_effort_unavailable"):
        asyncio.run(_bind(ex, _session(_model_opt("m1", current="m1"))))


def test_bind_skips_reasoning_when_unset() -> None:
    ex = AcpExecutor(entry_id="pi", model="entry-default")
    conn = _FakeConn()
    ex._conn = conn
    ex._acp_session_id = "sess"
    asyncio.run(_bind(ex, _session(_model_opt("m1", current="m1"), _thought_opt("off", "high"))))
    assert conn.calls == []
    assert ex._actual_reasoning_effort is None


async def _bind(ex: AcpExecutor, session: SimpleNamespace) -> None:
    latest = await ex._bind_model(session)
    await ex._bind_reasoning_effort(latest)


def test_acp_plugin_forwards_reasoning_effort_to_executor_and_l1() -> None:
    from bora.plugins.contrib.acp import AcpExecutorSPI

    spi = AcpExecutorSPI(
        options={"entry": "pi", "reasoning_effort": "high"},
        model="m",
    )
    assert spi._inner.reasoning_effort == "high"
    bound = spi.bind_to_target(
        SimpleNamespace(container_id="c", uid=1, gid=1, workdir="/w", home="/h")
    )
    assert bound._inner.reasoning_effort == "high"
