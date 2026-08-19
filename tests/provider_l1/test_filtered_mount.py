"""Filtered package mount hides evaluation/ from container view."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ageval.adapters.provider_docker import DockerProvider, ensure_image_lock
from ageval.runtime.identity import IdentityFactory

REPO = Path(__file__).resolve().parents[2]


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
                timeout=10,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="Docker daemon unavailable")


def test_evaluation_hidden_in_filtered_mount(tmp_path: Path) -> None:
    lock = ensure_image_lock(REPO)
    provider = DockerProvider(image_lock_path=lock)
    f = IdentityFactory()
    attempt = f.new_attempt(f.new_trial(f.new_run(), "sha256:" + "e" * 64))
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "visible.txt").write_text("ok\n", encoding="utf-8")
    (pkg / "evaluation").mkdir()
    (pkg / "evaluation" / "gold.json").write_text('{"secret":1}\n', encoding="utf-8")
    work = tmp_path / "work"
    runtime = provider.prepare(
        attempt,
        package_root=pkg,
        work_root=work,
        network_mode="none",
        hide_evaluation=True,
    )
    outcome = provider.run_command(
        runtime,
        [
            "python",
            "-c",
            "from pathlib import Path; "
            "print('eval', Path('/attempt/package/evaluation').exists()); "
            "print('vis', Path('/attempt/package/visible.txt').exists())",
        ],
        network=False,
        timeout_seconds=60,
    )
    provider.cleanup(runtime)
    assert outcome.exit_code == 0
    assert "eval False" in outcome.stdout_summary
    assert "vis True" in outcome.stdout_summary
