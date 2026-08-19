"""Generic image_contribute collect + bake (no plugin-named interpreter)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from ageval.adapters.provider_docker.types import DockerImageLock
from ageval.application.plugin_ops.image_contribute_bake import (
    ImageContributeError,
    apply_image_contribute_bake,
    bake_layer_content_digest,
    bake_plugin_layer,
    baked_image_tag,
    bound_executor_ids,
)
from ageval.config.model import LockedTaskConfig


def _lock_with_profiles(profiles: list[dict[str, Any]]) -> LockedTaskConfig:
    return cast(LockedTaskConfig, SimpleNamespace(agent_profiles=profiles))


def _base() -> DockerImageLock:
    return DockerImageLock(
        kind="t",
        platform="linux/arm64",
        image_tag="ageval-pkg:x",
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
    with (
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.collect_declares_for_lock",
            return_value=[{"plugin": "acp"}],
        ),
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.selected_contribute_plugin_ids",
            return_value=[],
        ),
    ):
        out, meta = apply_image_contribute_bake(
            lock=lock, base_image=_base(), platform="linux/arm64"
        )
    assert out.image_tag == "ageval-pkg:x"
    assert meta["status"] == "skipped"


def test_apply_fail_closed_when_bound_but_no_declare() -> None:
    lock = _lock_with_profiles(
        [{"id": "s", "executor": "nooa", "options": {"agent": "lib.agents:A"}}]
    )
    with (
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.collect_declares_for_lock",
            return_value=[],
        ),
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.selected_contribute_plugin_ids",
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
            "ageval.application.plugin_ops.image_contribute_bake.collect_declares_for_lock",
            return_value=[{"plugin": "nooa"}],
        ),
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.selected_contribute_plugin_ids",
            return_value=["nooa"],
        ),
        patch(
            "ageval.application.plugin_ops.image_contribute_bake._find_installed_plugin_root",
            return_value=None,
        ),
        pytest.raises(ImageContributeError) as ei,
    ):
        apply_image_contribute_bake(lock=lock, base_image=_base(), platform="linux/arm64")
    assert ei.value.kind == "plugin_not_ready"


def _plugin_root(tmp_path: Path, bake: str, files: dict[str, str] | None = None) -> Path:
    root = tmp_path / "plugin"
    df = root / "docker" / "Dockerfile.bake"
    df.parent.mkdir(parents=True, exist_ok=True)
    df.write_text(bake, encoding="utf-8")
    for rel, body in (files or {}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_bake_suffix_from_inputs_not_inspect_id(tmp_path: Path) -> None:
    root = _plugin_root(
        tmp_path,
        "FROM ${BASE_IMAGE}\nCOPY worker/x.py /opt/x.py\n",
        {"worker/x.py": "print(1)\n"},
    )
    df = root / "docker" / "Dockerfile.bake"
    first = bake_layer_content_digest(
        plugin_id="nooa",
        plugin_root=root,
        dockerfile=df,
        base_content_digest="sha256:d",
    )
    second = bake_layer_content_digest(
        plugin_id="nooa",
        plugin_root=root,
        dockerfile=df,
        base_content_digest="sha256:d",
    )
    assert first == second
    tag = baked_image_tag(_base(), "nooa", first)
    assert tag.startswith("ageval-pkg:x-nooa-")
    assert "abc" not in tag
    other_base = bake_layer_content_digest(
        plugin_id="nooa",
        plugin_root=root,
        dockerfile=df,
        base_content_digest="sha256:other",
    )
    assert other_base != first
    (root / "worker" / "x.py").write_text("print(2)\n", encoding="utf-8")
    assert (
        bake_layer_content_digest(
            plugin_id="nooa",
            plugin_root=root,
            dockerfile=df,
            base_content_digest="sha256:d",
        )
        != first
    )


def test_apply_fail_closed_when_bake_file_missing(tmp_path: Path) -> None:
    empty = tmp_path / "installed"
    empty.mkdir()
    lock = _lock_with_profiles([{"id": "s", "executor": "nooa"}])
    with (
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.collect_declares_for_lock",
            return_value=[{"plugin": "nooa"}],
        ),
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.selected_contribute_plugin_ids",
            return_value=["nooa"],
        ),
        patch(
            "ageval.application.plugin_ops.image_contribute_bake._find_installed_plugin_root",
            return_value=empty,
        ),
        pytest.raises(ImageContributeError) as ei,
    ):
        apply_image_contribute_bake(lock=lock, base_image=_base(), platform="linux/arm64")
    assert ei.value.kind == "plugin_not_ready"


def test_apply_reuses_baked_tag_without_inspect_suffix(tmp_path: Path) -> None:
    root = _plugin_root(
        tmp_path,
        "FROM ${BASE_IMAGE}\nCOPY worker/x.py /opt/x.py\n",
        {"worker/x.py": "print(1)\n"},
    )
    lock = _lock_with_profiles([{"id": "s", "executor": "nooa"}])
    baked = DockerImageLock(
        kind="docker-package-attempt",
        platform="linux/arm64",
        image_tag="ageval-pkg:x-nooa-deadbeefcaf0",
        image_digest="sha256:baked",
        build_input_digest="sha256:bake",
    )
    with (
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.collect_declares_for_lock",
            return_value=[{"plugin": "nooa"}],
        ),
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.selected_contribute_plugin_ids",
            return_value=["nooa"],
        ),
        patch(
            "ageval.application.plugin_ops.image_contribute_bake._find_installed_plugin_root",
            return_value=root,
        ),
        patch(
            "ageval.application.plugin_ops.image_contribute_bake.bake_plugin_layer",
            return_value=baked,
        ) as bake_layer,
    ):
        out, meta = apply_image_contribute_bake(
            lock=lock, base_image=_base(), platform="linux/arm64"
        )
    assert out.image_tag == baked.image_tag
    assert meta["status"] == "baked"
    out_tag = bake_layer.call_args.kwargs["out_tag"]
    assert out_tag.startswith("ageval-pkg:x-nooa-")
    assert "abc" not in out_tag
    assert _base().image_digest not in out_tag


def test_bake_plugin_layer_skips_buildx_when_tag_exists(tmp_path: Path) -> None:
    root = _plugin_root(
        tmp_path,
        "FROM ${BASE_IMAGE}\nCOPY worker/x.py /opt/x.py\n",
        {"worker/x.py": "print(1)\n"},
    )
    with patch(
        "ageval.application.plugin_ops.image_contribute_bake.inspect_image_digest",
        return_value="sha256:cached-bake",
    ):
        out = bake_plugin_layer(
            base_image=_base(),
            platform="linux/arm64",
            out_tag="ageval-pkg:x-nooa-abc123abc123",
            plugin_id="nooa",
            plugin_root=root,
        )
    assert out.image_digest == "sha256:cached-bake"
    assert out.image_tag == "ageval-pkg:x-nooa-abc123abc123"
    assert out.build_input_digest.startswith("sha256:")
