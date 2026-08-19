"""L1 host residual: default drop l1-work; --keep-workspace retains (issue #76)."""

from __future__ import annotations

from pathlib import Path

from ageval.application.attempt.run_l1 import drop_l1_work


def _seed_l1_work(run_dir: Path) -> Path:
    work = run_dir / "l1-work"
    (work / "workspace").mkdir(parents=True)
    (work / "package_view" / "vendor").mkdir(parents=True)
    (work / "workspace" / "out.txt").write_text("agent writable\n", encoding="utf-8")
    (work / "package_view" / "vendor" / "big.bin").write_bytes(b"\x00" * 64)
    # Hub-facing evidence sibling (must never be deleted by drop_l1_work).
    (run_dir / "result.json").write_text('{"status":"PASS"}\n', encoding="utf-8")
    (run_dir / "agent").mkdir()
    (run_dir / "agent" / "summary.json").write_text("{}\n", encoding="utf-8")
    return work


def test_drop_l1_work_default_removes_tree(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_a"
    run_dir.mkdir()
    work = _seed_l1_work(run_dir)

    drop_l1_work(run_dir, keep_workspace=False)

    assert not work.exists()
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "agent" / "summary.json").is_file()


def test_drop_l1_work_keep_workspace_retains_tree(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_b"
    run_dir.mkdir()
    work = _seed_l1_work(run_dir)

    drop_l1_work(run_dir, keep_workspace=True)

    assert work.is_dir()
    assert (work / "workspace" / "out.txt").is_file()
    assert (work / "package_view" / "vendor" / "big.bin").is_file()
    assert (run_dir / "result.json").is_file()


def test_drop_l1_work_noop_when_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_c"
    run_dir.mkdir()
    (run_dir / "result.json").write_text("{}\n", encoding="utf-8")

    drop_l1_work(run_dir, keep_workspace=False)

    assert not (run_dir / "l1-work").exists()
    assert (run_dir / "result.json").is_file()
