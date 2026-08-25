"""First-class usage plus sibling extra bags (observational, not PASS)."""

from __future__ import annotations

from ageval.evidence.usage import observational_bag, sealed_extra, sealed_usage, terminal_extra


def test_sealed_usage_omits_unknown_and_zeros_are_caller_owned() -> None:
    assert sealed_usage(prompt_tokens=3, completion_tokens=1) == {
        "prompt_tokens": 3,
        "completion_tokens": 1,
    }
    assert sealed_usage() is None


def test_sealed_extra_strips_first_class_keys() -> None:
    assert sealed_extra({"reasoning_tokens": 2, "prompt_tokens": 9}) == {"reasoning_tokens": 2}
    assert sealed_extra({}) is None


def test_terminal_extra_prefers_sibling_then_usage_extra() -> None:
    assert terminal_extra({"extra": {"foo": True}, "usage": {"extra": {"old": 1}}}) == {"foo": True}
    assert terminal_extra({"usage": {"prompt_tokens": 1, "extra": {"old": 1}}}) == {"old": 1}
    assert terminal_extra({"extra": {}, "usage": {"extra": {"old": 1}}}) == {"old": 1}
    assert terminal_extra({"usage": {"prompt_tokens": 1}}) is None
    assert observational_bag({}) is None
    assert observational_bag({"probe": {"foo": True}}) == {"probe": {"foo": True}}
