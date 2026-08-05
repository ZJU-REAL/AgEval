"""Provider L1 isolation contracts (replaces Application probe task_id paths)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bora.adapters.provider_docker import DockerProvider, DockerRuntime, ensure_image_lock
from bora.runtime.identity import IdentityFactory

REPO = Path(__file__).resolve().parents[2]


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "info"], check=False, capture_output=True, timeout=10
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="Docker daemon unavailable")


def _attempt():
    f = IdentityFactory()
    return f.new_attempt(f.new_trial(f.new_run(), "sha256:" + "a" * 64))


def test_filtered_mount_hides_evaluation_gold(tmp_path: Path) -> None:
    """Gold under package evaluation/ is not visible in container (hide_evaluation)."""
    lock = ensure_image_lock(REPO)
    provider = DockerProvider(image_lock_path=lock)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "visible.txt").write_text("ok\n", encoding="utf-8")
    (pkg / "evaluation").mkdir()
    (pkg / "evaluation" / "gold.json").write_text('{"secret":1}\n', encoding="utf-8")
    runtime = provider.prepare(
        _attempt(),
        package_root=pkg,
        work_root=tmp_path / "work",
        network_mode="none",
        hide_evaluation=True,
    )
    out = provider.run_command(
        runtime,
        [
            "python",
            "-c",
            "import json; from pathlib import Path; "
            "seen = Path('/attempt/package/evaluation').exists() or "
            "Path('/attempt/package/evaluation/gold.json').is_file(); "
            "print(json.dumps({'seen_gold': seen, 'eval_visible': seen, "
            "'visible': Path('/attempt/package/visible.txt').is_file()}))",
        ],
        network=False,
        timeout_seconds=60,
        writer_name="harness",
    )
    provider.cleanup(runtime)
    assert out.exit_code == 0
    import json

    probe = json.loads(out.stdout_summary.strip().splitlines()[-1])
    assert probe["seen_gold"] is False
    assert probe["eval_visible"] is False
    assert probe["visible"] is True
    assert out.writer_stop_confirmed is True


def test_harness_run_without_cred_mount_and_network_none(tmp_path: Path) -> None:
    """Harness command: no /creds mount, no key env, network none blocks egress."""
    lock = ensure_image_lock(REPO)
    provider = DockerProvider(image_lock_path=lock)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    work = tmp_path / "work"
    runtime = provider.prepare(
        _attempt(),
        package_root=pkg,
        work_root=work,
        network_mode="none",
        hide_evaluation=True,
    )
    # Deliberately do not pass credentials_root / env with keys.
    out = provider.run_command(
        runtime,
        [
            "python",
            "-c",
            "import json, os, urllib.request; from pathlib import Path; "
            "cred = Path('/creds').exists(); "
            "key = bool(os.environ.get('OPENAI_API_KEY') or os.environ.get('CODEX_HOME')); "
            "net = False\n"
            "try:\n"
            " urllib.request.urlopen('https://example.com', timeout=2); net = True\n"
            "except Exception:\n"
            " net = False\n"
            "print(json.dumps({'cred_visible': cred, 'key_env': key, 'network_ok': net}))",
        ],
        network=False,
        timeout_seconds=60,
        writer_name="harness",
    )
    provider.cleanup(runtime)
    import json

    probe = json.loads(out.stdout_summary.strip().splitlines()[-1])
    assert probe.get("cred_visible") is False
    assert probe.get("key_env") is False
    assert probe.get("network_ok") is False
    assert out.writer_stop_confirmed is True


def test_writer_stop_unconfirmed_until_recorded() -> None:
    """Barrier fact: unstopped writer keeps writer_stop_confirmed false."""
    attempt = _attempt()
    rt = DockerRuntime(attempt=attempt)
    rt.register_writer("background")
    assert rt.writer_stop_confirmed is False
    rt.record_writer_stop(False)
    assert rt.writer_stop_confirmed is False
    rt.record_writer_stop(True)
    # all() over [False, True] => still False
    assert rt.writer_stop_confirmed is False
    rt2 = DockerRuntime(attempt=_attempt())
    rt2.register_writer("w1")
    rt2.record_writer_stop(True)
    assert rt2.writer_stop_confirmed is True
