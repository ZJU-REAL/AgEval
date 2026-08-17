"""Official L1 base apt/pip mirror knobs are build inputs, not task identity."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from bora.adapters.provider_docker import images
from bora.adapters.provider_docker.official_base import (
    BUILD_INPUT_NAMES,
    official_attempt_dir,
    official_build_input_digest,
    official_buildx_command,
    prepare_official_build_env,
)

REPO = Path(__file__).resolve().parents[2]
ATTEMPT = official_attempt_dir(REPO)


def _load_sitecustomize() -> ModuleType:
    path = ATTEMPT / "sitecustomize.py"
    spec = importlib.util.spec_from_file_location("bora_attempt_sitecustomize", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_attempt(root: Path) -> Path:
    dest = official_attempt_dir(root)
    dest.mkdir(parents=True)
    for name in BUILD_INPUT_NAMES:
        (dest / name).write_bytes((ATTEMPT / name).read_bytes())
    return dest


def _write_lock(path: Path, digest: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kind": "docker-attempt",
                "platform": "linux/arm64",
                "image_tag": "bora-attempt:l1",
                "image_digest": "sha256:img",
                "build_input_digest": digest,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_digest_stable_for_empty_mirrors() -> None:
    first = official_build_input_digest(ATTEMPT)
    second = official_build_input_digest(ATTEMPT, apt_mirror="", pip_index="")
    assert first == second
    assert len(first) == 64


def test_digest_changes_when_either_mirror_changes() -> None:
    empty = official_build_input_digest(ATTEMPT)
    apt = official_build_input_digest(ATTEMPT, apt_mirror="http://mirrors.example/debian")
    pip = official_build_input_digest(ATTEMPT, pip_index="https://pypi.example/simple")
    both = official_build_input_digest(
        ATTEMPT,
        apt_mirror="http://mirrors.example/debian",
        pip_index="https://pypi.example/simple",
    )
    assert empty != apt != pip != both
    assert apt != both
    assert pip != both


def test_prepare_env_process_wins_over_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "BORA_APT_MIRROR=http://from-file/debian\nBORA_PIP_INDEX=https://from-file/simple\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BORA_APT_MIRROR", "http://from-process/debian")
    monkeypatch.delenv("BORA_PIP_INDEX", raising=False)
    apt, pip = prepare_official_build_env(tmp_path)
    assert apt == "http://from-process/debian"
    assert pip == "https://from-file/simple"


def test_buildx_command_always_passes_both_args() -> None:
    cmd = official_buildx_command(
        dockerfile=ATTEMPT / "Dockerfile",
        tag="bora-attempt:l1",
        platform="linux/arm64",
        context=ATTEMPT,
        apt_mirror="http://mirrors.example/debian",
        pip_index="",
    )
    assert cmd[:3] == ["docker", "buildx", "build"]
    assert "--build-arg" in cmd
    assert "BORA_APT_MIRROR=http://mirrors.example/debian" in cmd
    assert "BORA_PIP_INDEX=" in cmd


def test_official_dockerfile_rewrites_before_install_executors() -> None:
    text = (ATTEMPT / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG BORA_APT_MIRROR" in text
    assert "ARG BORA_PIP_INDEX" in text
    assert "ENV PIP_INDEX_URL" not in text
    assert text.index("ARG BORA_APT_MIRROR") < text.index("COPY install-executors.sh")
    assert text.index("/etc/pip.conf") < text.index("COPY install-executors.sh")
    assert text.index("99bora-no-proxy") < text.index("COPY install-executors.sh")
    assert "COPY sitecustomize.py" in text
    assert text.index("COPY sitecustomize.py") < text.index("COPY install-executors.sh")
    assert "if [ -f /etc/pip.conf ]" in text


def test_sitecustomize_noop_without_pip_conf(tmp_path: Path) -> None:
    apply = _load_sitecustomize().apply_pip_mirror_env
    env = {
        "HTTP_PROXY": "http://dead.proxy:1",
        "HTTPS_PROXY": "http://dead.proxy:1",
    }
    apply(conf=tmp_path / "missing.conf", environ=env)
    assert env["HTTP_PROXY"] == "http://dead.proxy:1"
    assert "PIP_INDEX_URL" not in env


def test_sitecustomize_drops_proxy_and_sets_index(tmp_path: Path) -> None:
    apply = _load_sitecustomize().apply_pip_mirror_env
    conf = tmp_path / "pip.conf"
    conf.write_text(
        "[global]\nindex-url = https://pypi.example/simple\ntrusted-host = pypi.example\n",
        encoding="utf-8",
    )
    env = {
        "HTTP_PROXY": "http://dead.proxy:1",
        "HTTPS_PROXY": "http://dead.proxy:1",
        "http_proxy": "http://dead.proxy:1",
    }
    apply(conf=conf, environ=env)
    assert "HTTP_PROXY" not in env
    assert "HTTPS_PROXY" not in env
    assert "http_proxy" not in env
    assert env["PIP_INDEX_URL"] == "https://pypi.example/simple"
    assert env["NO_PROXY"] == "*"


def test_sitecustomize_guard_is_site_hook_name() -> None:
    text = (ATTEMPT / "sitecustomize.py").read_text(encoding="utf-8")
    assert 'if __name__ == "sitecustomize"' in text
    other = _load_sitecustomize()
    assert other.__name__ == "bora_attempt_sitecustomize"


def test_ensure_image_lock_skips_when_digest_and_image_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = _seed_attempt(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BORA_APT_MIRROR", raising=False)
    monkeypatch.delenv("BORA_PIP_INDEX", raising=False)
    digest = "sha256:" + official_build_input_digest(attempt)
    lock_path = tmp_path / ".bora" / "runtime-images" / "provider-l1.json"
    _write_lock(lock_path, digest)

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("official base rebuild should be skipped")

    monkeypatch.setattr(images, "inspect_image_digest", lambda _tag: "sha256:present")
    monkeypatch.setattr(images.subprocess, "run", boom)
    assert images.ensure_image_lock(tmp_path) == lock_path


def test_ensure_image_lock_rebuilds_when_image_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = _seed_attempt(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BORA_APT_MIRROR", raising=False)
    monkeypatch.delenv("BORA_PIP_INDEX", raising=False)
    digest = "sha256:" + official_build_input_digest(attempt)
    lock_path = tmp_path / ".bora" / "runtime-images" / "provider-l1.json"
    _write_lock(lock_path, digest)
    called: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: Any) -> Any:
        called.append(list(cmd))
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(images, "inspect_image_digest", lambda _tag: None)
    monkeypatch.setattr(images.subprocess, "run", fake_run)
    assert images.ensure_image_lock(tmp_path) == lock_path
    assert called


def test_ensure_image_lock_rebuilds_when_mirror_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = _seed_attempt(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BORA_APT_MIRROR", raising=False)
    monkeypatch.delenv("BORA_PIP_INDEX", raising=False)
    empty = "sha256:" + official_build_input_digest(attempt)
    lock_path = tmp_path / ".bora" / "runtime-images" / "provider-l1.json"
    _write_lock(lock_path, empty)
    monkeypatch.setenv("BORA_APT_MIRROR", "http://mirrors.example/debian")
    called: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: Any) -> Any:
        called.append(list(cmd))
        new = official_build_input_digest(attempt, apt_mirror="http://mirrors.example/debian")
        _write_lock(lock_path, "sha256:" + new)
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(images, "inspect_image_digest", lambda _tag: "sha256:present")
    monkeypatch.setattr(images.subprocess, "run", fake_run)
    assert images.ensure_image_lock(tmp_path) == lock_path
    assert called
    assert any(str(tmp_path / "docker" / "attempt" / "build.py") in cmd for cmd in called)


def test_package_buildx_does_not_receive_mirror_args(tmp_path: Path) -> None:
    from unittest.mock import patch

    from bora.adapters.provider_docker.types import DockerImageLock

    df = tmp_path / "environment" / "Dockerfile"
    df.parent.mkdir(parents=True)
    df.write_text("FROM bora-attempt:l1\n", encoding="utf-8")
    base = DockerImageLock(
        kind="docker-attempt",
        platform="linux/arm64",
        image_tag="bora-attempt:l1",
        image_digest="sha256:official",
        build_input_digest="sha256:official-in",
    )
    cmds: list[list[str]] = []
    built = False

    def fake_run(cmd: list[str], **_kwargs: Any) -> Any:
        nonlocal built
        cmds.append(list(cmd))
        if cmd[:3] == ["docker", "image", "inspect"]:
            if built:
                return type("P", (), {"returncode": 0, "stdout": "sha256:new\n", "stderr": ""})()
            return type("P", (), {"returncode": 1, "stdout": "", "stderr": "missing"})()
        if cmd[:2] == ["docker", "buildx"]:
            built = True
            return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        raise AssertionError(cmd)

    with (
        patch.object(images, "ensure_base_image", return_value=base),
        patch.object(images.subprocess, "run", side_effect=fake_run),
    ):
        images.build_package_image(package_root=tmp_path, platform="linux/arm64")

    buildx = [cmd for cmd in cmds if cmd[:2] == ["docker", "buildx"]]
    assert buildx
    joined = " ".join(buildx[0])
    assert "BORA_APT_MIRROR" not in joined
    assert "BORA_PIP_INDEX" not in joined
