"""publish_tree registers; it does not copy or exclude."""

from __future__ import annotations

from pathlib import Path

from ageval_sdk.context import RunContext, RunParameterView, RunScope


def test_publish_tree_registers_without_copying(tmp_path: Path) -> None:
    source = tmp_path / "workspace"
    source.mkdir()
    (source / "a.txt").write_text("x\n", encoding="utf-8")
    ctx = RunContext(
        params=RunParameterView({}),
        scope=RunScope(attempt_id="a", trial_id="t", run_id="r"),
        workspace_root=source,
        artifact_dir=tmp_path / "artifacts",
    )
    registered = ctx.publish_tree("repo", source)
    assert registered == source
    assert ctx.published["repo"] == source
    assert not (tmp_path / "artifacts" / "repo").exists()
