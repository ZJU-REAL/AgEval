from __future__ import annotations

from tests.hub.model_join import join_overlay, load_pin, overlay_candidates


def test_pin_exists_and_is_versioned():
    pin = load_pin()
    assert pin["format"] == "ageval.model-pin/1"
    assert pin["models"]
    assert "alibaba/qwen-max" in pin["models"]
    assert "deepseek/deepseek-v4-flash" in pin["models"]


def test_dashscope_qwen_max_unique_joins():
    pin = load_pin()
    hit = join_overlay("dashscope/qwen-max", pin)
    assert hit["canonical"] == "alibaba/qwen-max"
    assert hit["hits"] == ["alibaba/qwen-max"]


def test_opencode_openrouter_nested_joins():
    pin = load_pin()
    hit = join_overlay("openrouter/deepseek/deepseek-v4-flash", pin)
    assert hit["canonical"] == "deepseek/deepseek-v4-flash"


def test_openai_dashscope_double_prefix():
    pin = load_pin()
    hit = join_overlay("openai/dashscope/qwen3.8-max", pin)
    assert hit["canonical"] == "alibaba/qwen3.8-max"


def test_flash_family_is_exact_not_fuzzy():
    pin = load_pin()
    assert join_overlay("qwen-flash", pin)["canonical"] == "alibaba/qwen-flash"
    assert join_overlay("qwen3.6-flash", pin)["canonical"] == "alibaba/qwen3.6-flash"
    assert join_overlay("qwen3.8-flash", pin)["canonical"] == "alibaba/qwen3.8-flash"
    assert join_overlay("flash", pin)["canonical"] is None
    assert join_overlay("max", pin)["canonical"] is None


def test_missing_pin_does_not_join():
    hit = join_overlay("dashscope/qwen-max", None)
    assert hit["canonical"] is None
    empty = join_overlay(
        "dashscope/qwen-max",
        {
            "format": "ageval.model-pin/1",
            "models": {},
            "prefixes": ["dashscope"],
            "lookup": {},
            "aliases": {},
        },
    )
    assert empty["canonical"] is None


def test_alias_pins_ambiguous_overlay():
    pin = load_pin()
    pin = {
        **pin,
        "aliases": {"acme/flash": "alibaba/qwen-flash"},
    }
    hit = join_overlay("acme/flash", pin)
    assert hit["canonical"] == "alibaba/qwen-flash"


def test_candidates_longest_first():
    pin = load_pin()
    cands = overlay_candidates(
        "openrouter/deepseek/deepseek-v4-flash", list(pin["prefixes"])
    )
    assert cands[0] == "openrouter/deepseek/deepseek-v4-flash"
    assert "deepseek/deepseek-v4-flash" in cands
    assert "deepseek-v4-flash" in cands
