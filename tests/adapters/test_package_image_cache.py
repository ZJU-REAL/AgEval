"""Package Attempt image cache key: content, not lock.digest / task_id."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from ageval.adapters.provider_docker.images import (
    build_package_image,
    package_image_content_digest,
    package_local_tag,
    parse_dockerfile_copy_sources,
    parse_dockerfile_from_image,
)
from ageval.adapters.provider_docker.types import DockerImageLock


def _write_pkg(root: Path, dockerfile: str, files: dict[str, str] | None = None) -> Path:
    df = root / "environment" / "Dockerfile"
    df.parent.mkdir(parents=True, exist_ok=True)
    df.write_text(dockerfile, encoding="utf-8")
    for rel, body in (files or {}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return df


def test_parse_from_and_copy_skips_from_stage() -> None:
    text = "\n".join(
        [
            "FROM ageval-attempt:l1",
            "COPY environment/tool.sh /usr/local/bin/tool",
            "COPY --from=builder /opt/x /opt/x",
            'COPY ["src/a.py", "src/b.py", "/app/"]',
        ]
    )
    assert parse_dockerfile_from_image(text) == "ageval-attempt:l1"
    assert parse_dockerfile_copy_sources(text) == [
        "environment/tool.sh",
        "src/a.py",
        "src/b.py",
    ]


def test_content_digest_stable_and_ignores_unrelated_files(tmp_path: Path) -> None:
    df = _write_pkg(
        tmp_path,
        "FROM ageval-attempt:l1\nCOPY environment/tool.sh /bin/tool\n",
        {"environment/tool.sh": "echo ok\n"},
    )
    first = package_image_content_digest(
        dockerfile=df,
        package_root=tmp_path,
        platform="linux/arm64",
        base_digest="sha256:base",
    )
    (tmp_path / "task.yaml").write_text("id: other\n", encoding="utf-8")
    (tmp_path / "profiles.yaml").write_text("x: 1\n", encoding="utf-8")
    second = package_image_content_digest(
        dockerfile=df,
        package_root=tmp_path,
        platform="linux/arm64",
        base_digest="sha256:base",
    )
    assert first == second
    assert package_local_tag(first) == f"ageval-pkg:{first[:12]}"
    assert "task" not in package_local_tag(first)


def test_content_digest_changes_with_dockerfile_copy_or_base(tmp_path: Path) -> None:
    df = _write_pkg(
        tmp_path,
        "FROM ageval-attempt:l1\nCOPY environment/tool.sh /bin/tool\n",
        {"environment/tool.sh": "echo a\n"},
    )
    kwargs: dict[str, Any] = {
        "dockerfile": df,
        "package_root": tmp_path,
        "platform": "linux/arm64",
        "base_digest": "sha256:base",
    }
    original = package_image_content_digest(**kwargs)
    (tmp_path / "environment" / "tool.sh").write_text("echo b\n", encoding="utf-8")
    assert package_image_content_digest(**kwargs) != original
    df.write_text("FROM ageval-attempt:l1\nRUN true\n", encoding="utf-8")
    (tmp_path / "environment" / "tool.sh").write_text("echo a\n", encoding="utf-8")
    assert package_image_content_digest(**kwargs) != original
    df.write_text(
        "FROM ageval-attempt:l1\nCOPY environment/tool.sh /bin/tool\n",
        encoding="utf-8",
    )
    assert (
        package_image_content_digest(
            dockerfile=df,
            package_root=tmp_path,
            platform="linux/arm64",
            base_digest="sha256:other",
        )
        != original
    )


def test_build_skips_buildx_when_tag_exists(tmp_path: Path) -> None:
    _write_pkg(tmp_path, "FROM ageval-attempt:l1\n")
    base = DockerImageLock(
        kind="docker-attempt",
        platform="linux/arm64",
        image_tag="ageval-attempt:l1",
        image_digest="sha256:official",
        build_input_digest="sha256:official-in",
    )
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> object:
        calls.append(list(cmd))
        if cmd[:3] == ["docker", "image", "inspect"]:
            return type("P", (), {"returncode": 0, "stdout": "sha256:cached\n", "stderr": ""})()
        raise AssertionError(f"unexpected docker command: {cmd}")

    with (
        patch(
            "ageval.adapters.provider_docker.images.ensure_base_image",
            return_value=base,
        ),
        patch("ageval.adapters.provider_docker.images.subprocess.run", side_effect=fake_run),
    ):
        lock = build_package_image(package_root=tmp_path, platform="linux/arm64")

    assert lock.image_digest == "sha256:cached"
    assert lock.image_tag.startswith("ageval-pkg:")
    assert "task" not in lock.image_tag
    assert all("buildx" not in cmd for cmd in calls)
    assert lock.build_input_digest.startswith("sha256:")


def test_build_runs_buildx_on_cache_miss(tmp_path: Path) -> None:
    _write_pkg(tmp_path, "FROM ageval-attempt:l1\n")
    base = DockerImageLock(
        kind="docker-attempt",
        platform="linux/arm64",
        image_tag="ageval-attempt:l1",
        image_digest="sha256:official",
        build_input_digest="sha256:official-in",
    )
    seen_buildx = False

    def fake_run(cmd: list[str], **_kwargs: object) -> object:
        nonlocal seen_buildx
        if cmd[:3] == ["docker", "image", "inspect"]:
            if seen_buildx:
                return type("P", (), {"returncode": 0, "stdout": "sha256:new\n", "stderr": ""})()
            return type("P", (), {"returncode": 1, "stdout": "", "stderr": "missing"})()
        if cmd[:2] == ["docker", "buildx"]:
            seen_buildx = True
            return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        raise AssertionError(f"unexpected docker command: {cmd}")

    with (
        patch(
            "ageval.adapters.provider_docker.images.ensure_base_image",
            return_value=base,
        ),
        patch("ageval.adapters.provider_docker.images.subprocess.run", side_effect=fake_run),
    ):
        lock = build_package_image(package_root=tmp_path, platform="linux/arm64")

    assert seen_buildx is True
    assert lock.image_digest == "sha256:new"
    assert lock.image_tag.startswith("ageval-pkg:")
