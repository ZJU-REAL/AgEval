"""DockerProvider unit/integration tests."""

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


def _attempt():
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, "sha256:" + "d" * 64)
    return f.new_attempt(trial)


def test_prepare_run_cleanup(tmp_path: Path) -> None:
    lock = ensure_image_lock(REPO)
    provider = DockerProvider(image_lock_path=lock)
    attempt = _attempt()
    # Use a tiny package dir
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "hello.txt").write_text("hi\n", encoding="utf-8")
    work = tmp_path / "work"
    runtime = provider.prepare(
        attempt,
        package_root=pkg,
        work_root=work,
        network_mode="none",
    )
    outcome = provider.run_command(
        runtime,
        [
            "python",
            "-c",
            "from pathlib import Path; print(Path('/attempt/package/hello.txt').read_text())",
        ],
        timeout_seconds=60,
        network=False,
    )
    # Single-container probe is not full L1 Attempt isolation.
    assert outcome.assurance == "l0"
    assert outcome.exit_code == 0
    assert "hi" in outcome.stdout_summary
    assert outcome.writer_stop_confirmed is True  # docker run waited for exit
    assert outcome.detail.get("containment") == "single_container_probe"
    provider.cleanup(runtime)
    assert runtime.cleaned
