"""First-party ACP reuses ageval-attempt:l1; extra Dockerfile layers still build."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from ageval.adapters.provider_docker.images import is_official_base_noop_dockerfile
from ageval.adapters.provider_docker.types import DockerImageLock
from ageval.application.plugin_ops.image_contribute_bake import (
    apply_image_contribute_bake,
    baked_image_tag,
    plugin_id_for_image_tag,
    should_reuse_official_attempt_image,
)
from ageval.config.model import LockedTaskConfig


def _lock(profiles: list[dict[str, Any]]) -> LockedTaskConfig:
    return cast(LockedTaskConfig, SimpleNamespace(agent_profiles=profiles))


def _base() -> DockerImageLock:
    return DockerImageLock(
        kind="docker-attempt",
        platform="linux/arm64",
        image_tag="ageval-attempt:l1",
        image_digest="sha256:official",
        build_input_digest="sha256:official-in",
    )


def test_noop_dockerfile_detection() -> None:
    assert is_official_base_noop_dockerfile("FROM ageval-attempt:l1\n")
    assert is_official_base_noop_dockerfile("# comment\nFROM ageval-attempt:l1 AS base\n")
    assert not is_official_base_noop_dockerfile("FROM ageval-attempt:l1\nCOPY x /x\n")
    assert not is_official_base_noop_dockerfile("FROM ageval-attempt:l1\nRUN true\n")
    assert not is_official_base_noop_dockerfile("FROM other:latest\n")


def test_reuse_official_acp_from_only() -> None:
    lock = _lock([{"id": "s", "executor": "acp", "options": {"entry": "pi"}}])
    with patch(
        "ageval.application.plugin_ops.image_contribute_bake.selected_contribute_plugin_ids",
        return_value=[],
    ):
        assert should_reuse_official_attempt_image(lock, "FROM ageval-attempt:l1\n") is True


def test_copy_or_run_still_builds_package_tag() -> None:
    lock = _lock([{"id": "s", "executor": "acp", "options": {"entry": "pi"}}])
    with patch(
        "ageval.application.plugin_ops.image_contribute_bake.selected_contribute_plugin_ids",
        return_value=[],
    ):
        assert (
            should_reuse_official_attempt_image(
                lock, "FROM ageval-attempt:l1\nCOPY environment/tool.sh /bin/tool\n"
            )
            is False
        )
        assert (
            should_reuse_official_attempt_image(lock, "FROM ageval-attempt:l1\nRUN true\n") is False
        )


def test_external_executor_does_not_reuse() -> None:
    lock = _lock([{"id": "s", "executor": "dsh"}])
    with patch(
        "ageval.application.plugin_ops.image_contribute_bake.selected_contribute_plugin_ids",
        return_value=["dsh"],
    ):
        assert should_reuse_official_attempt_image(lock, "FROM ageval-attempt:l1\n") is False


def test_selected_bake_does_not_reuse() -> None:
    lock = _lock(
        [
            {
                "id": "s",
                "executor": "acp",
                "options": {"entry": "pi"},
                "extensions": [{"plugin": "dsh", "slots": ["image_contribute"]}],
            }
        ]
    )
    with patch(
        "ageval.application.plugin_ops.image_contribute_bake.selected_contribute_plugin_ids",
        return_value=["dsh"],
    ):
        assert should_reuse_official_attempt_image(lock, "FROM ageval-attempt:l1\n") is False


def test_apply_acp_only_does_not_bake_installed_declares() -> None:
    lock = _lock([{"id": "s", "executor": "acp", "options": {"entry": "pi"}}])
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
    assert out.image_tag == "ageval-attempt:l1"
    assert meta["status"] == "skipped"
    assert meta["baked"] == []


def test_prepare_reuses_official_tag_without_buildx(
    tmp_path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    import ageval.application.attempt.extension_hooks as hooks
    import ageval.application.attempt.run_l1_prepare as prep
    import ageval.application.plugin_ops.image_contribute_bake as bake
    from ageval.application.attempt.run_l1_prepare import prepare_l1_runtime
    from ageval.runtime.identity import IdentityFactory

    (tmp_path / "environment").mkdir()
    (tmp_path / "environment" / "Dockerfile").write_text(
        "FROM ageval-attempt:l1\n", encoding="utf-8"
    )
    official = _base()

    class FakeDocker:
        def __init__(self, *, image_lock_path):  # type: ignore[no-untyped-def]
            del image_lock_path

        def prepare(self, attempt, **_kwargs):  # type: ignore[no-untyped-def]
            from ageval.adapters.provider_docker.types import DockerRuntime

            return DockerRuntime(
                attempt=attempt,
                image_lock=official,
                workdir_host=tmp_path / "work",
            )

    def _must_not_build(**_kwargs: object) -> DockerImageLock:
        raise AssertionError("must not build package image")

    monkeypatch.setattr(prep, "ensure_base_image", lambda _cwd: official)
    monkeypatch.setattr(prep, "build_package_image", _must_not_build)
    monkeypatch.setattr(prep, "ensure_image_lock", lambda _cwd: tmp_path / "lock.json")
    monkeypatch.setattr(prep, "DockerProvider", FakeDocker)
    monkeypatch.setattr(hooks, "hook_prepare", lambda *_a, **_k: None)
    monkeypatch.setattr(
        bake, "apply_image_contribute_bake", lambda **kw: (kw["base_image"], {"status": "skipped"})
    )
    monkeypatch.setattr(bake, "should_reuse_official_attempt_image", lambda *_a, **_k: True)

    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, "sha256:" + "a" * 64)
    lock = SimpleNamespace(
        digest="sha256:" + "a" * 64,
        task_id="terminal-jsonl-agg",
        provider={"kind": "docker", "dockerfile": "environment/Dockerfile"},
        agent_profiles=[{"id": "s", "executor": "acp", "options": {"entry": "pi"}}],
    )
    _docker, runtime, meta = prepare_l1_runtime(
        tmp_path,
        lock,
        tmp_path / "run",
        attempt=factory.new_attempt(trial),
    )
    assert runtime.image_lock is not None
    assert runtime.image_lock.image_tag == "ageval-attempt:l1"
    assert meta["image_tag"] == "ageval-attempt:l1"


def test_namespaced_plugin_id_in_bake_tag() -> None:
    assert plugin_id_for_image_tag("acme/nooa") == "acme--nooa"
    tag = baked_image_tag(_base(), "acme/nooa", "d" * 24)
    assert tag.startswith("ageval-attempt:l1-acme--nooa-")
    assert "/" not in tag.split(":", 1)[1]
