"""Plugin bake layers forward AGEVAL_PIP_INDEX as PIP_INDEX_URL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ageval.plugins.contrib.docker import images


class _FakeDaemon:
    def __init__(self) -> None:
        self.images: set[str] = set()
        self.builds: list[tuple[str, ...]] = []

    def __call__(self, *args: str, timeout: float = 600.0) -> subprocess.CompletedProcess[str]:
        del timeout
        if args[:2] == ("image", "inspect"):
            tag = args[2]
            if tag in self.images:
                return subprocess.CompletedProcess(
                    list(args), 0, stdout=f"sha256:{tag}\n", stderr=""
                )
            return subprocess.CompletedProcess(list(args), 1, stdout="", stderr="missing")
        if args[:2] == ("buildx", "build"):
            self.builds.append(args)
            tag = args[args.index("-t") + 1]
            self.images.add(tag)
            return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
        if args[0] == "tag":
            src, dest = args[1], args[2]
            if src in self.images:
                self.images.add(dest)
                return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
            return subprocess.CompletedProcess(list(args), 1, stdout="", stderr="missing src")
        return subprocess.CompletedProcess(list(args), 1, stdout="", stderr=f"unexpected {args}")


def _plugin_tree(tmp_path: Path) -> tuple[Path, tuple[tuple[str, str, str, str], ...]]:
    task_root = tmp_path / "task"
    task_root.mkdir()
    (task_root / "Dockerfile").write_text("FROM ageval-attempt:base\n", encoding="utf-8")
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    bake = plugin / "Dockerfile.bake"
    bake.write_text(
        "ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\nARG PIP_INDEX_URL=\n",
        encoding="utf-8",
    )
    body = bake.read_text(encoding="utf-8")
    layers = (("nooa", str(bake), str(plugin), body),)
    return task_root, layers


def test_plugin_bake_pip_index_empty_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGEVAL_PIP_INDEX", raising=False)
    assert images.plugin_bake_pip_index() == ""
    assert images.plugin_layer_build_args("ageval-pkg:base") == ("BASE_IMAGE=ageval-pkg:base",)


def test_plugin_bake_pip_index_strips_and_forwards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGEVAL_PIP_INDEX", "  https://pypi.tuna.tsinghua.edu.cn/simple  ")
    assert images.plugin_bake_pip_index() == "https://pypi.tuna.tsinghua.edu.cn/simple"
    assert images.plugin_layer_build_args("ageval-pkg:base") == (
        "BASE_IMAGE=ageval-pkg:base",
        "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple",
    )


def test_whitespace_only_index_is_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGEVAL_PIP_INDEX", "   ")
    assert images.plugin_bake_pip_index() == ""
    assert "PIP_INDEX_URL" not in " ".join(images.plugin_layer_build_args("ageval-pkg:base"))


def test_build_argv_omits_pip_index_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGEVAL_PIP_INDEX", raising=False)
    fake = _FakeDaemon()
    monkeypatch.setattr(images, "docker", fake)
    task_root, layers = _plugin_tree(tmp_path)

    images.build_task_image(
        task_root=task_root,
        dockerfile_rel="Dockerfile",
        platform="linux/arm64",
        base_digest="sha256:base",
        force_build=True,
        plugin_layers=layers,
    )

    assert len(fake.builds) == 2
    recipe_argv, plugin_argv = fake.builds
    recipe_tag = recipe_argv[recipe_argv.index("-t") + 1]
    assert "--build-arg" not in recipe_argv
    assert "PIP_INDEX_URL" not in " ".join(plugin_argv)
    assert f"BASE_IMAGE={recipe_tag}" in plugin_argv


def test_build_argv_forwards_pip_index_only_on_plugin_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = "https://pypi.tuna.tsinghua.edu.cn/simple"
    monkeypatch.setenv("AGEVAL_PIP_INDEX", index)
    fake = _FakeDaemon()
    monkeypatch.setattr(images, "docker", fake)
    task_root, layers = _plugin_tree(tmp_path)

    images.build_task_image(
        task_root=task_root,
        dockerfile_rel="Dockerfile",
        platform="linux/arm64",
        base_digest="sha256:base",
        force_build=True,
        plugin_layers=layers,
    )

    recipe_argv, plugin_argv = fake.builds
    assert "--build-arg" not in recipe_argv
    joined = " ".join(plugin_argv)
    assert f"--build-arg PIP_INDEX_URL={index}" in joined
    assert "--build-arg BASE_IMAGE=" in joined


def test_pip_index_changes_plugin_layer_tag_not_recipe_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeDaemon()
    monkeypatch.setattr(images, "docker", fake)
    task_root, layers = _plugin_tree(tmp_path)
    kwargs = {
        "task_root": task_root,
        "dockerfile_rel": "Dockerfile",
        "platform": "linux/arm64",
        "base_digest": "sha256:base",
        "force_build": True,
    }

    monkeypatch.delenv("AGEVAL_PIP_INDEX", raising=False)
    tag_unset, _ = images.build_task_image(plugin_layers=layers, **kwargs)
    tag_recipe, _ = images.build_task_image(plugin_layers=(), **kwargs)

    monkeypatch.setenv("AGEVAL_PIP_INDEX", "https://pypi.tuna.tsinghua.edu.cn/simple")
    tag_set, _ = images.build_task_image(plugin_layers=layers, **kwargs)
    tag_recipe_set, _ = images.build_task_image(plugin_layers=(), **kwargs)

    assert tag_unset != tag_set
    assert tag_recipe == tag_recipe_set


def test_contrib_bake_recipes_declare_pip_index_arg() -> None:
    root = Path(__file__).resolve().parents[2] / "plugins"
    bakes = sorted(root.glob("*/docker/Dockerfile.bake"))
    assert bakes, "expected contrib Dockerfile.bake files"
    for bake in bakes:
        text = bake.read_text(encoding="utf-8")
        assert "ARG PIP_INDEX_URL=" in text, bake
