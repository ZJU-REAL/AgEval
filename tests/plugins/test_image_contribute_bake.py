"""Generic image_contribute collect + bake (no plugin-named interpreter)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from bora.adapters.provider_docker.types import DockerImageLock
from bora.application.plugin_ops.image_contribute_bake import (
    ImageContributeError,
    apply_image_contribute_bake,
    bound_executor_ids,
)
from bora.config.model import LockedTaskConfig


def _lock_with_profiles(profiles: list[dict[str, Any]]) -> LockedTaskConfig:
    return cast(LockedTaskConfig, SimpleNamespace(agent_profiles=profiles))


def _base() -> DockerImageLock:
    return DockerImageLock(
        kind="t",
        platform="linux/arm64",
        image_tag="bora-pkg:x",
        image_digest="sha256:abc",
        build_input_digest="sha256:d",
    )


def test_bound_executor_ids() -> None:
    lock = _lock_with_profiles(
        [
            {"id": "s", "executor": "nooa", "options": {"agent": "x:Y"}},
            {"id": "t", "executor": "acp"},
            {"id": "u", "executor": "nooa"},
        ]
    )
    assert bound_executor_ids(lock) == ["nooa", "acp"]


def test_apply_skips_first_party_only() -> None:
    lock = _lock_with_profiles([{"id": "s", "executor": "acp"}])
    with patch(
        "bora.application.plugin_ops.image_contribute_bake.collect_declares_for_lock",
        return_value=[{"plugin": "acp"}],
    ):
        out, meta = apply_image_contribute_bake(
            lock=lock, base_image=_base(), platform="linux/arm64"
        )
    assert out.image_tag == "bora-pkg:x"
    assert meta["status"] == "skipped"


def test_apply_fail_closed_when_bound_but_no_declare() -> None:
    lock = _lock_with_profiles(
        [{"id": "s", "executor": "nooa", "options": {"agent": "lib.agents:A"}}]
    )
    with (
        patch(
            "bora.application.plugin_ops.image_contribute_bake.collect_declares_for_lock",
            return_value=[],
        ),
        pytest.raises(ImageContributeError) as ei,
    ):
        apply_image_contribute_bake(lock=lock, base_image=_base(), platform="linux/arm64")
    assert ei.value.kind == "image_contribute_unsatisfied"


def test_apply_fail_closed_when_not_installed() -> None:
    lock = _lock_with_profiles(
        [{"id": "s", "executor": "nooa", "options": {"agent": "lib.agents:A"}}]
    )
    with (
        patch(
            "bora.application.plugin_ops.image_contribute_bake.collect_declares_for_lock",
            return_value=[{"plugin": "nooa"}],
        ),
        patch(
            "bora.application.plugin_ops.image_contribute_bake._find_installed_plugin_root",
            return_value=None,
        ),
        pytest.raises(ImageContributeError) as ei,
    ):
        apply_image_contribute_bake(lock=lock, base_image=_base(), platform="linux/arm64")
    assert ei.value.kind == "plugin_not_ready"
