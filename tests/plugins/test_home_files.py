"""home-files dest safety, overwrite, and directory merge."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "plugins" / "home-files" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from home_files.hooks import HomeFilesError, apply_files  # noqa: E402


def _ctx(tmp: Path) -> dict[str, Path]:
    pkg = tmp / "db"
    ws = tmp / "ws"
    cred = tmp / "cred"
    pkg.mkdir()
    ws.mkdir()
    cred.mkdir()
    (cred / "home_overlay").mkdir()
    return {"package_root": pkg, "workspace_root": ws, "cred_root": cred}


def test_file_overwrite_home(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    src = ctx["package_root"] / "overlays" / "a.json"
    src.parent.mkdir()
    src.write_text('{"v":1}\n', encoding="utf-8")
    dest = ctx["cred_root"] / "home_overlay" / ".config" / "x.json"
    dest.parent.mkdir(parents=True)
    dest.write_text("old\n", encoding="utf-8")
    apply_files(
        [{"src": "overlays/a.json", "dest": ".config/x.json", "dest_root": "home"}],
        {k: str(v) for k, v in ctx.items()},
    )
    assert dest.read_text(encoding="utf-8") == '{"v":1}\n'


def test_directory_merge_keeps_extra(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    src_dir = ctx["package_root"] / "overlays" / "skills"
    (src_dir / "foo").mkdir(parents=True)
    (src_dir / "foo" / "SKILL.md").write_text("new\n", encoding="utf-8")
    dest_dir = ctx["workspace_root"] / ".agents" / "skills"
    (dest_dir / "foo").mkdir(parents=True)
    (dest_dir / "foo" / "SKILL.md").write_text("old\n", encoding="utf-8")
    (dest_dir / "keep").mkdir()
    (dest_dir / "keep" / "x.md").write_text("stay\n", encoding="utf-8")
    apply_files(
        [{"src": "overlays/skills", "dest": ".agents/skills", "dest_root": "workspace"}],
        {k: str(v) for k, v in ctx.items()},
    )
    assert (dest_dir / "foo" / "SKILL.md").read_text(encoding="utf-8") == "new\n"
    assert (dest_dir / "keep" / "x.md").read_text(encoding="utf-8") == "stay\n"


def test_reject_parent_and_absolute(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    payload = {k: str(v) for k, v in ctx.items()}
    with pytest.raises(HomeFilesError) as ei:
        apply_files(
            [{"src": "../secret", "dest": "x", "dest_root": "home"}],
            payload,
        )
    assert ei.value.kind == "home_files_path_invalid"
    with pytest.raises(HomeFilesError) as ei:
        apply_files(
            [{"src": "/etc/passwd", "dest": "x", "dest_root": "home"}],
            payload,
        )
    assert ei.value.kind == "home_files_path_invalid"
    with pytest.raises(HomeFilesError) as ei:
        apply_files(
            [{"src": "overlays/a", "dest": "../escape", "dest_root": "home"}],
            payload,
        )
    assert ei.value.kind == "home_files_path_invalid"


def test_reject_evaluation_dest(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    src = ctx["package_root"] / "overlays" / "gold.json"
    src.parent.mkdir()
    src.write_text("{}\n", encoding="utf-8")
    with pytest.raises(HomeFilesError) as ei:
        apply_files(
            [
                {
                    "src": "overlays/gold.json",
                    "dest": "evaluation/gold.json",
                    "dest_root": "workspace",
                }
            ],
            {k: str(v) for k, v in ctx.items()},
        )
    assert ei.value.kind == "home_files_dest_invalid"


def test_dest_file_src_dir_fails(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    src_dir = ctx["package_root"] / "overlays" / "dir"
    src_dir.mkdir(parents=True)
    (src_dir / "a.txt").write_text("x\n", encoding="utf-8")
    dest = ctx["workspace_root"] / "out"
    dest.write_text("file\n", encoding="utf-8")
    with pytest.raises(HomeFilesError) as ei:
        apply_files(
            [{"src": "overlays/dir", "dest": "out", "dest_root": "workspace"}],
            {k: str(v) for k, v in ctx.items()},
        )
    assert ei.value.kind == "home_files_dest_invalid"


def test_journeys_overlay_profile_locks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2]
    profiles = root / "examples/journeys/acp-profiles/profiles.acp.opencode.qwen3.8-max.yaml"
    if not profiles.is_file():
        pytest.skip("journeys overlay profiles were removed")
    from ageval.plugins import bootstrap as boot
    from ageval.plugins.registry import reset_global_registry
    from ageval.plugins.store import install_from_path

    home = tmp_path / "ageval-home"
    home.mkdir()
    monkeypatch.setenv("AGEVAL_HOME", str(home))
    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    install_from_path(Path(__file__).resolve().parents[2] / "plugins" / "home-files")

    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["AGEVAL_HOME"] = str(home)
    # Overlay profiles expand ${litellm_base_url}; CI has no repo .env.
    env.setdefault("litellm_api_key", "ci-test-key")
    env.setdefault("litellm_base_url", "http://127.0.0.1:9")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
            "lock",
            str(root / "examples/journeys"),
            "--task",
            "terminal-jsonl-agg",
            "--profiles",
            str(root / "examples/journeys/acp-profiles/profiles.acp.opencode.qwen3.8-max.yaml"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    data = json.loads(proc.stdout)
    solver = data["extension_bindings"]["solver"]
    plugins = {
        item.get("plugin")
        for item in (solver["slots"].get("after_environment_ready") or {}).get("chain") or []
    }
    assert "home-files" in plugins


def test_symlink_child_outside_src_fails(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    src_dir = ctx["package_root"] / "overlays" / "skills"
    src_dir.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (src_dir / "link").symlink_to(outside)
    with pytest.raises(HomeFilesError) as ei:
        apply_files(
            [{"src": "overlays/skills", "dest": ".agents/skills", "dest_root": "workspace"}],
            {k: str(v) for k, v in ctx.items()},
        )
    assert ei.value.kind == "home_files_path_invalid"


def test_dest_root_required(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    src = ctx["package_root"] / "overlays" / "a.json"
    src.parent.mkdir()
    src.write_text("{}\n", encoding="utf-8")
    with pytest.raises(HomeFilesError) as ei:
        apply_files(
            [{"src": "overlays/a.json", "dest": "x.json"}],
            {k: str(v) for k, v in ctx.items()},
        )
    assert ei.value.kind == "home_files_dest_invalid"
