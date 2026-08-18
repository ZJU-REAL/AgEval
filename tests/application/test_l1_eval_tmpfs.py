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
    assert cmd[cmd.index("--entrypoint") + 1] == "python"
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


def test_evaluate_l1_reuse_attempt_skips_new_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bora.application.attempt.attempt_stages import AttemptStageContext
    from bora.application.attempt.run_l1_phases import evaluate_l1

    isolated: dict[str, Any] = {}
    reused: dict[str, Any] = {}

    def _fake_isolated(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        isolated.update(kwargs)
        return ({"status": "PASS", "score": 1.0}, {"ok": True, "writer_stop_confirmed": True})

    def _fake_reuse(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        reused.update(kwargs)
        return (
            {"status": "FAIL", "score": 0.0, "metrics": {}},
            {"ok": True, "writer_stop_confirmed": True, "reuse_attempt": True},
        )

    monkeypatch.setattr(
        "bora.application.attempt.run_l1_phases.run_clean_evaluator_container",
        _fake_isolated,
    )
    monkeypatch.setattr(
        "bora.application.attempt.run_l1_phases.run_reuse_attempt_evaluator",
        _fake_reuse,
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
    lock = SimpleNamespace(evaluation={"reuse_attempt": True, "network": "bridge", "tmpfs_mb": 256})
    runtime = SimpleNamespace(
        image_lock=SimpleNamespace(image_tag="bora-pkg:test"),
        writer_inventory=[],
        writer_stop_confirmed=True,
        agent_container_ids=["cid-live"],
        target_ledger=None,
        container_id=None,
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
    assert isolated == {}
    assert reused["container_id"] == "cid-live"
    assert ctx.evaluator_raw is not None
    assert ctx.evaluator_raw["status"] == "FAIL"
    assert ctx.l1_meta["eval_placement"]["reuse_attempt"] is True
    assert ctx.l1_meta["eval_placement"]["network"] == "bridge"


def test_seal_l1_inputs_copies_hidden_package_path(tmp_path: Path) -> None:
    from bora.application.attempt.attempt_stages import AttemptStageContext
    from bora.application.attempt.run_l1_phases import seal_l1_inputs

    pkg = tmp_path / "pkg"
    ev = pkg / "evaluation"
    ev.mkdir(parents=True)
    gold = ev / "hidden.json"
    gold.write_text('{"gold": 1}\n', encoding="utf-8")
    (pkg / "evaluator.py").write_text("def evaluate(ctx): ...\n", encoding="utf-8")
    art = tmp_path / "session-output.json"
    art.write_text("{}\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    lock = SimpleNamespace(
        evaluation={
            "inputs": [
                {"artifact": "session-output", "target": "artifacts/session-output.json"},
                {"package_path": "evaluation/hidden.json", "target": "hidden.json"},
            ]
        }
    )
    ctx = AttemptStageContext(
        package_root=pkg,
        lock=lock,
        run_dir=run_dir,
        runtime=SimpleNamespace(writer_stop_confirmed=True),
        harness_out={
            "envelope": {
                "ok": True,
                "terminal": {"kind": "completed"},
                "published": {"session-output": str(art)},
            }
        },
    )
    assert seal_l1_inputs(ctx) is True
    staging = run_dir / "eval_staging"
    assert (staging / "hidden.json").read_text(encoding="utf-8") == '{"gold": 1}\n'
    # Agent package view is a filtered host copy; gold stays out of package_root
    # until this host staging step (then docker cp at eval).
    assert not (pkg / "package_view").exists()


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
