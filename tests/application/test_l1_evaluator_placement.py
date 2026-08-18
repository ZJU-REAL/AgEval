"""writable placement flips /tmp exec; tmpfs size stays evaluation.tmpfs_mb."""

from __future__ import annotations

from pathlib import Path

from bora.application.attempt.run_l1_evaluator import (
    clean_eval_tmpfs_mount,
    run_clean_evaluator_container,
)
from bora.config.eval_placement import resolve_eval_placement


def test_clean_eval_tmpfs_mount_exec_flag() -> None:
    assert clean_eval_tmpfs_mount(32) == "/tmp:rw,noexec,nosuid,size=32m"
    assert clean_eval_tmpfs_mount(4096, allow_exec=True) == "/tmp:rw,exec,nosuid,size=4096m"


def test_writable_run_sets_workdir_env(tmp_path: Path, monkeypatch: object) -> None:
    from types import SimpleNamespace
    from typing import Any

    captured: dict[str, Any] = {}

    def _run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        captured["cmd"] = list(cmd)
        captured["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(returncode=0, stdout='{"status":"PASS","score":1.0}\n', stderr="")

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "bora.application.attempt.run_l1_evaluator.subprocess.run",
        _run,
    )
    spec = resolve_eval_placement(
        {"placement": "writable", "tmpfs_mb": 4096, "timeout_seconds": 180}
    )
    staging = tmp_path / "eval"
    staging.mkdir()
    run_clean_evaluator_container(
        image_tag="img",
        staging=staging,
        artifact_filename="patch.diff",
        artifact_key="patch",
        expected_filename=None,
        tmpfs_mb=spec.tmpfs_mb,
        placement=spec,
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--tmpfs") + 1] == "/tmp:rw,exec,nosuid,size=4096m"
    assert cmd[cmd.index("--network") + 1] == "none"
    assert cmd[cmd.index("--entrypoint") + 1] == "python"
    assert "BORA_EVAL_WORKDIR=/tmp/eval-work" in cmd
    assert captured["timeout"] == 180.0


def test_bridge_run_sets_network(tmp_path: Path, monkeypatch: object) -> None:
    from types import SimpleNamespace
    from typing import Any

    captured: dict[str, Any] = {}

    def _run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        captured["cmd"] = list(cmd)
        return SimpleNamespace(returncode=0, stdout='{"status":"PASS","score":1.0}\n', stderr="")

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "bora.application.attempt.run_l1_evaluator.subprocess.run",
        _run,
    )
    spec = resolve_eval_placement({"network": "bridge", "tmpfs_mb": 32})
    staging = tmp_path / "eval"
    staging.mkdir()
    run_clean_evaluator_container(
        image_tag="img",
        staging=staging,
        artifact_filename="out.json",
        artifact_key="out",
        expected_filename=None,
        tmpfs_mb=spec.tmpfs_mb,
        placement=spec,
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--network") + 1] == "bridge"
    assert "--read-only" in cmd
    assert not any(part.startswith("/creds") or ":/creds" in part for part in cmd)
