"""L1 clean-eval applies evaluation.tmpfs_mb to /tmp tmpfs (not Attempt /tmp)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from bora.application.attempt.run_l1_evaluator import (
    clean_eval_tmpfs_mount,
    run_clean_evaluator_container,
)
from bora.config.constants import DEFAULT_EVAL_TMPFS_MB


def test_clean_eval_tmpfs_mount_default_and_override() -> None:
    assert clean_eval_tmpfs_mount(DEFAULT_EVAL_TMPFS_MB) == "/tmp:rw,noexec,nosuid,size=32m"
    assert clean_eval_tmpfs_mount(256) == "/tmp:rw,noexec,nosuid,size=256m"


@pytest.mark.parametrize("bad", [0, -1, True, 32.5, "256", None])
def test_clean_eval_tmpfs_mount_rejects_bad(bad: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        clean_eval_tmpfs_mount(bad)  # type: ignore[arg-type]


def test_run_clean_evaluator_uses_declared_tmpfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def _run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        captured["cmd"] = list(cmd)
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout='{"status":"PASS","score":1.0}\n', stderr="")

    monkeypatch.setattr(
        "bora.application.attempt.run_l1_evaluator.subprocess.run",
        _run,
    )
    staging = tmp_path / "eval"
    staging.mkdir()
    raw, meta = run_clean_evaluator_container(
        image_tag="bora-attempt:l1",
        staging=staging,
        artifact_filename="workspace-snapshot.tar.gz",
        artifact_key="workspace-snapshot",
        expected_filename=None,
        tmpfs_mb=256,
    )
    assert raw["status"] == "PASS"
    assert meta["ok"] is True
    cmd = captured["cmd"]
    assert cmd[:2] == ["docker", "run"]
    idx = cmd.index("--tmpfs")
    assert cmd[idx + 1] == "/tmp:rw,noexec,nosuid,size=256m"
    assert "--read-only" in cmd
    assert "size=32m" not in cmd
    assert "size=64m" not in cmd


def test_run_clean_evaluator_defaults_to_32m(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[str]] = {}

    def _run(cmd: list[str], **_kwargs: object) -> SimpleNamespace:
        captured["cmd"] = list(cmd)
        return SimpleNamespace(returncode=0, stdout='{"status":"PASS","score":1.0}\n', stderr="")

    monkeypatch.setattr(
        "bora.application.attempt.run_l1_evaluator.subprocess.run",
        _run,
    )
    staging = tmp_path / "eval"
    staging.mkdir()
    run_clean_evaluator_container(
        image_tag="bora-attempt:l1",
        staging=staging,
        artifact_filename="out.json",
        artifact_key="out",
        expected_filename=None,
    )
    idx = captured["cmd"].index("--tmpfs")
    assert captured["cmd"][idx + 1] == "/tmp:rw,noexec,nosuid,size=32m"


def test_evaluate_l1_passes_lock_tmpfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bora.application.attempt.attempt_stages import AttemptStageContext
    from bora.application.attempt.run_l1_phases import evaluate_l1

    captured: dict[str, Any] = {}

    def _fake_eval(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        captured.update(kwargs)
        return (
            {"status": "PASS", "score": 1.0, "metrics": {}},
            {"ok": True, "writer_stop_confirmed": True},
        )

    monkeypatch.setattr(
        "bora.application.attempt.run_l1_phases.run_clean_evaluator_container",
        _fake_eval,
    )
    monkeypatch.setattr(
        "bora.application.attempt.extension_hooks.hook_evaluation_input",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "bora.application.attempt.extension_hooks.hook_evaluation_runtime",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "bora.application.attempt.extension_hooks.hook_score_postprocess",
        lambda _lock, raw: raw,
    )

    src = tmp_path / "art.json"
    src.write_text("{}", encoding="utf-8")
    staging = tmp_path / "eval_staging"
    staging.mkdir()
    lock = SimpleNamespace(evaluation={"tmpfs_mb": 256})
    runtime = SimpleNamespace(
        image_lock=SimpleNamespace(image_tag="bora-pkg:test"),
        writer_inventory=[],
        writer_stop_confirmed=True,
    )
    ctx = AttemptStageContext(
        package_root=tmp_path,
        lock=lock,
        run_dir=tmp_path,
        runtime=runtime,
        artifacts_map={
            "artifact_key": "workspace-snapshot",
            "artifact_filename": "workspace-snapshot.tar.gz",
            "src": str(src),
        },
    )
    evaluate_l1(ctx)
    assert captured["tmpfs_mb"] == 256
    assert captured["image_tag"] == "bora-pkg:test"


def test_run_clean_evaluator_rejects_bad_tmpfs_before_docker(tmp_path: Path) -> None:
    staging = tmp_path / "eval"
    staging.mkdir()
    with pytest.raises(ValueError, match="positive integer"):
        run_clean_evaluator_container(
            image_tag="bora-attempt:l1",
            staging=staging,
            artifact_filename="out.json",
            artifact_key="out",
            expected_filename=None,
            tmpfs_mb=0,
        )
