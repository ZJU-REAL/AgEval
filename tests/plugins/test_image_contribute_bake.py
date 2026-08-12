"""Spec 05 Phase 2: image_contribute collect + bake decision logic."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from bora.adapters.provider_docker.types import DockerImageLock
from bora.application.image_contribute_bake import (
    ImageContributeError,
    apply_image_contribute_bake,
    needs_nooa_bake,
    nooa_bound,
)
from bora.config.model import LockedTaskConfig


def _lock_with_profiles(profiles: list[dict[str, Any]]) -> LockedTaskConfig:
    return cast(LockedTaskConfig, SimpleNamespace(agent_profiles=profiles))


def test_needs_nooa_bake_from_declare() -> None:
    assert needs_nooa_bake([{"plugin": "nooa", "bake": ["nooa", "bora-executor-nooa"]}])
    assert needs_nooa_bake([{"bake": "bora-executor-nooa"}])
    assert not needs_nooa_bake([{"plugin": "acp", "bake": "acp_entries"}])
    assert not needs_nooa_bake([])


def test_nooa_bound() -> None:
    lock = _lock_with_profiles([{"id": "s", "executor": "nooa", "options": {"agent": "x:Y"}}])
    assert nooa_bound(lock)
    lock2 = _lock_with_profiles([{"id": "s", "executor": "acp"}])
    assert not nooa_bound(lock2)


def test_apply_skips_when_not_nooa() -> None:
    base = DockerImageLock(
        kind="t",
        platform="linux/arm64",
        image_tag="bora-pkg:x",
        image_digest="sha256:abc",
        build_input_digest="sha256:d",
    )
    lock = _lock_with_profiles([{"id": "s", "executor": "acp"}])
    with patch(
        "bora.application.image_contribute_bake.collect_declares_for_lock",
        return_value=[{"plugin": "acp", "bake": "acp_entries"}],
    ):
        out, meta = apply_image_contribute_bake(lock=lock, base_image=base, platform="linux/arm64")
    assert out is base
    assert meta["status"] == "skipped_no_nooa"


def test_apply_fail_closed_when_bound_but_no_declare() -> None:
    base = DockerImageLock(
        kind="t",
        platform="linux/arm64",
        image_tag="bora-pkg:x",
        image_digest="sha256:abc",
        build_input_digest="sha256:d",
    )
    lock = _lock_with_profiles(
        [{"id": "s", "executor": "nooa", "options": {"agent": "lib.agents:A"}}]
    )
    with (
        patch(
            "bora.application.image_contribute_bake.collect_declares_for_lock",
            return_value=[],
        ),
        pytest.raises(ImageContributeError) as ei,
    ):
        apply_image_contribute_bake(lock=lock, base_image=base, platform="linux/arm64")
    assert ei.value.kind == "image_contribute_unsatisfied"


def test_apply_fail_closed_when_not_installed() -> None:
    base = DockerImageLock(
        kind="t",
        platform="linux/arm64",
        image_tag="bora-pkg:x",
        image_digest="sha256:abc",
        build_input_digest="sha256:d",
    )
    lock = _lock_with_profiles(
        [{"id": "s", "executor": "nooa", "options": {"agent": "lib.agents:A"}}]
    )
    declares: list[Any] = [{"plugin": "nooa", "bake": ["nooa"]}]
    with (
        patch(
            "bora.application.image_contribute_bake.collect_declares_for_lock",
            return_value=declares,
        ),
        patch(
            "bora.application.image_contribute_bake._find_installed_plugin_root",
            return_value=None,
        ),
        pytest.raises(ImageContributeError) as ei,
    ):
        apply_image_contribute_bake(lock=lock, base_image=base, platform="linux/arm64")
    assert ei.value.kind == "plugin_not_ready"
