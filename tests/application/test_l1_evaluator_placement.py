"""writable placement flips /tmp exec; tmpfs size stays evaluation.tmpfs_mb."""

from __future__ import annotations

from pathlib import Path

from ageval.application.attempt.run_l1_evaluator import (
    clean_eval_tmpfs_mount,
    run_clean_evaluator_container,
)
from ageval.config.eval_placement import resolve_eval_placement


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
        "ageval.application.attempt.run_l1_evaluator.subprocess.run",
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
    assert "AGEVAL_EVAL_WORKDIR=/tmp/eval-work" in cmd
    assert captured["timeout"] == 180.0


def test_bridge_run_sets_network(tmp_path: Path, monkeypatch: object) -> None:
    from types import SimpleNamespace
    from typing import Any

    captured: dict[str, Any] = {}

    def _run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        captured["cmd"] = list(cmd)
        return SimpleNamespace(returncode=0, stdout='{"status":"PASS","score":1.0}\n', stderr="")

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "ageval.application.attempt.run_l1_evaluator.subprocess.run",
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


def test_reuse_attempt_exec_not_new_container(tmp_path: Path, monkeypatch: object) -> None:
    from types import SimpleNamespace

    from ageval.application.attempt.run_l1_evaluator import run_reuse_attempt_evaluator

    captured: list[list[str]] = []

    def _run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        captured.append(list(cmd))
        if cmd[:2] == ["docker", "exec"] and "-c" in cmd:
            return SimpleNamespace(
                returncode=0, stdout='{"status":"FAIL","score":0.0}\n', stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "ageval.application.attempt.run_l1_evaluator.subprocess.run",
        _run,
    )
    spec = resolve_eval_placement({"reuse_attempt": True, "network": "bridge", "tmpfs_mb": 32})
    staging = tmp_path / "eval"
    staging.mkdir()
    (staging / "evaluator.py").write_text("def evaluate(ctx): return {}\n", encoding="utf-8")
    raw, meta = run_reuse_attempt_evaluator(
        container_id="cid-live",
        staging=staging,
        artifact_filename="out.json",
        artifact_key="out",
        expected_filename="expected.json",
        placement=spec,
        uid_gid="12000:12000",
        actor_home="/actor-homes/default",
    )
    assert raw["status"] == "FAIL"
    assert raw["score"] == 0.0
    assert meta["reuse_attempt"] is True
    assert any(cmd[:2] == ["docker", "cp"] for cmd in captured)
    helpers = [cmd for cmd in captured if cmd[:2] == ["docker", "run"]]
    assert len(helpers) == 1
    helper = helpers[0]
    assert "--privileged" in helper
    assert helper[helper.index("--user") + 1] == "0:0"
    assert helper[helper.index("--entrypoint") + 1] == "nsenter"
    assert "--pid" in helper
    assert helper[helper.index("--pid") + 1] == "container:cid-live"
    assert helper[helper.index("--network") + 1] == "none"
    assert "/creds" in helper
    execs = [cmd for cmd in captured if cmd[:2] == ["docker", "exec"]]
    assert execs
    python_exec = [cmd for cmd in execs if "python" in cmd]
    assert python_exec
    cmd = python_exec[0]
    assert "env" in cmd and "-i" in cmd
    assert cmd[cmd.index("-u") + 1] == "12000:12000"
    assert "--network" not in cmd
    assert "-e" not in cmd
    env_assigns = [part for part in cmd if "=" in part and part.split("=", 1)[0].isidentifier()]
    assert env_assigns == [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME=/actor-homes/default",
        "PYTHONUSERBASE=/actor-homes/default/.local",
    ]
    assert "HOME=/tmp" not in cmd
    assert not any(part == "/creds" for part in cmd)
    assert not any(cmd[:3] == ["docker", "network", "connect"] for cmd in captured)
    assert not any("--read-only" in cmd for cmd in captured)


def test_reuse_attempt_hide_creds_failure_is_error(tmp_path: Path, monkeypatch: object) -> None:
    from types import SimpleNamespace

    from ageval.application.attempt.run_l1_evaluator import run_reuse_attempt_evaluator

    captured: list[list[str]] = []

    def _run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        captured.append(list(cmd))
        if cmd[:2] == ["docker", "run"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="nsenter: denied")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "ageval.application.attempt.run_l1_evaluator.subprocess.run",
        _run,
    )
    spec = resolve_eval_placement({"reuse_attempt": True, "tmpfs_mb": 32})
    staging = tmp_path / "eval"
    staging.mkdir()
    raw, meta = run_reuse_attempt_evaluator(
        container_id="cid-live",
        staging=staging,
        artifact_filename="out.json",
        artifact_key="out",
        expected_filename=None,
        placement=spec,
    )
    assert raw["status"] == "ERROR"
    assert raw["metrics"]["error"] == "eval_creds_hide_failed"
    assert meta["ok"] is False
    assert not any("python" in cmd for cmd in captured)


def test_reuse_attempt_exec_env_includes_actor_user_site(
    tmp_path: Path, monkeypatch: object
) -> None:
    from types import SimpleNamespace

    from ageval.application.attempt.run_l1_evaluator import run_reuse_attempt_evaluator

    captured: list[list[str]] = []

    def _run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        captured.append(list(cmd))
        if cmd[:2] == ["docker", "exec"] and "python" in cmd:
            return SimpleNamespace(
                returncode=0, stdout='{"status":"PASS","score":1.0}\n', stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "ageval.application.attempt.run_l1_evaluator.subprocess.run",
        _run,
    )
    spec = resolve_eval_placement({"reuse_attempt": True, "tmpfs_mb": 32})
    staging = tmp_path / "eval"
    staging.mkdir()
    run_reuse_attempt_evaluator(
        container_id="cid-live",
        staging=staging,
        artifact_filename="out.json",
        artifact_key="out",
        expected_filename=None,
        placement=spec,
        uid_gid="12000:12000",
        actor_home="/actor-homes/default",
    )
    python_exec = [cmd for cmd in captured if cmd[:2] == ["docker", "exec"] and "python" in cmd]
    assert python_exec
    cmd = python_exec[0]
    assert "env" in cmd and "-i" in cmd
    assert cmd[cmd.index("-u") + 1] == "12000:12000"
    assert "HOME=/actor-homes/default" in cmd
    assert "PYTHONUSERBASE=/actor-homes/default/.local" in cmd
    assert "HOME=/tmp" not in cmd
    keys = [part.split("=", 1)[0] for part in cmd if "=" in part]
    assert "API_KEY" not in keys
    assert "TOKEN" not in keys
    assert "SECRET" not in keys
