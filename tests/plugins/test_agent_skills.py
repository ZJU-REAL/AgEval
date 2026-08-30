"""agent-skills dest expansion and fail-closed cases."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HF = Path(__file__).resolve().parents[2] / "plugins" / "home-files" / "src"
_AS = Path(__file__).resolve().parents[2] / "plugins" / "agent-skills" / "src"
for _p in (_HF, _AS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agent_skills.hooks import AgentSkillsError, expand_files  # noqa: E402
from home_files.hooks import apply_files  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _ctx(tmp: Path) -> dict[str, str]:
    pkg = tmp / "db"
    ws = tmp / "ws"
    cred = tmp / "cred"
    pkg.mkdir()
    ws.mkdir()
    cred.mkdir()
    (cred / "home_overlay").mkdir()
    skill = pkg / "overlays" / "skills" / "jsonl-review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# jsonl-review\n", encoding="utf-8")
    (pkg / "overlays").mkdir(exist_ok=True)
    (pkg / "overlays" / "AGENTS.md").write_text("use jsonl-review\n", encoding="utf-8")
    (pkg / "overlays" / "CLAUDE.md").write_text("claude notes\n", encoding="utf-8")
    return {
        "package_root": str(pkg),
        "workspace_root": str(ws),
        "cred_root": str(cred),
    }


def test_expand_generic_and_bound_entry() -> None:
    files = expand_files(
        {"skills": [{"src": "overlays/skills/jsonl-review"}]},
        {"acp_entries": ["opencode"]},
    )
    dests = {(row["dest_root"], row["dest"]) for row in files}
    assert ("home", ".agents/skills/jsonl-review") in dests
    assert ("home", ".config/opencode/skills/jsonl-review") in dests
    assert all(row["dest_root"] == "home" for row in files)


def test_codex_and_pi_prefixes() -> None:
    files = expand_files(
        {"skills": [{"src": "overlays/skills/jsonl-review"}]},
        {"acp_entries": ["codex", "pi"]},
    )
    dests = {row["dest"] for row in files}
    assert ".agents/skills/jsonl-review" in dests
    assert ".codex/skills/jsonl-review" in dests
    assert ".pi/agent/skills/jsonl-review" in dests


def test_grok_build_is_generic_only() -> None:
    files = expand_files(
        {"skills": [{"src": "overlays/skills/jsonl-review"}]},
        {"acp_entries": ["grok-build"]},
    )
    dests = {row["dest"] for row in files}
    assert dests == {".agents/skills/jsonl-review"}


def test_same_entry_dedups_dest() -> None:
    files = expand_files(
        {"skills": [{"src": "overlays/skills/jsonl-review"}]},
        {"acp_entries": ["codex", "codex"]},
    )
    dests = [row["dest"] for row in files]
    assert dests.count(".codex/skills/jsonl-review") == 1


def test_instructions_workspace_agents_and_codex_home() -> None:
    files = expand_files(
        {"instructions": [{"src": "overlays/AGENTS.md"}]},
        {"acp_entries": ["codex"]},
    )
    dests = {(row["dest_root"], row["dest"]) for row in files}
    assert ("workspace", "AGENTS.md") in dests
    assert ("home", ".codex/AGENTS.md") in dests
    assert ("home", "AGENTS.md") not in dests


def test_unknown_entry_fail_closed() -> None:
    with pytest.raises(AgentSkillsError) as ei:
        expand_files(
            {"skills": [{"src": "overlays/skills/jsonl-review"}]},
            {"acp_entries": ["not-an-entry"]},
        )
    assert ei.value.kind == "agent_skills_entry_invalid"


def test_author_dest_rejected() -> None:
    with pytest.raises(AgentSkillsError) as ei:
        expand_files(
            {"skills": [{"src": "overlays/skills/jsonl-review", "dest": "evil"}]},
            {"acp_entries": []},
        )
    assert ei.value.kind == "agent_skills_options_invalid"


def test_missing_skill_md_fail_closed(tmp_path: Path) -> None:
    from agent_skills.hooks import _assert_skill_markdown

    ctx = _ctx(tmp_path)
    bad = Path(ctx["package_root"]) / "overlays" / "skills" / "empty"
    bad.mkdir(parents=True)
    files = expand_files({"skills": [{"src": "overlays/skills/empty"}]}, {"acp_entries": []})
    with pytest.raises(AgentSkillsError) as ei:
        _assert_skill_markdown(files, ctx)
    assert ei.value.kind == "agent_skills_skill_invalid"


def test_path_escape_rejected(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    files = expand_files(
        {"skills": [{"src": "../secret"}]},
        {"acp_entries": []},
    )
    with pytest.raises(Exception) as ei:
        apply_files(files, ctx)
    assert getattr(ei.value, "kind", "") == "home_files_path_invalid"


def test_apply_writes_home_and_workspace(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    files = expand_files(
        {
            "dest_roots": ["home", "workspace"],
            "skills": [{"src": "overlays/skills/jsonl-review"}],
            "instructions": [{"src": "overlays/AGENTS.md"}],
        },
        {"acp_entries": ["codex"]},
    )
    apply_files(files, ctx)
    home = Path(ctx["cred_root"]) / "home_overlay"
    ws = Path(ctx["workspace_root"])
    assert (home / ".agents" / "skills" / "jsonl-review" / "SKILL.md").is_file()
    assert (home / ".codex" / "skills" / "jsonl-review" / "SKILL.md").is_file()
    assert (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8") == "use jsonl-review\n"
    assert (ws / ".agents" / "skills" / "jsonl-review" / "SKILL.md").is_file()
    assert (ws / "AGENTS.md").read_text(encoding="utf-8") == "use jsonl-review\n"


def test_does_not_collide_with_home_files_litellm(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    pkg = Path(ctx["package_root"])
    catalog = pkg / "overlays" / "opencode.litellm.json"
    catalog.write_text('{"ok": true}\n', encoding="utf-8")
    apply_files(
        [
            {
                "src": "overlays/opencode.litellm.json",
                "dest": ".config/opencode/opencode.json",
                "dest_root": "home",
            }
        ],
        ctx,
    )
    files = expand_files(
        {"skills": [{"src": "overlays/skills/jsonl-review"}]},
        {"acp_entries": ["opencode"]},
    )
    apply_files(files, ctx)
    home = Path(ctx["cred_root"]) / "home_overlay"
    assert (home / ".config" / "opencode" / "opencode.json").read_text(
        encoding="utf-8"
    ) == '{"ok": true}\n'
    assert (home / ".config" / "opencode" / "skills" / "jsonl-review" / "SKILL.md").is_file()


@pytest.fixture()
def ageval_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "ageval-home"
    home.mkdir()
    monkeypatch.setenv("AGEVAL_HOME", str(home))
    from ageval.plugins import bootstrap as boot
    from ageval.plugins.registry import reset_global_registry

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    return home


def test_install_agent_skills_pulls_home_files(ageval_home: Path) -> None:
    env = {**os.environ, "AGEVAL_HOME": str(ageval_home)}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
            "plugin",
            "install",
            str(ROOT / "plugins" / "agent-skills"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    ids = {row["plugin_id"] for row in data["installed"]}
    assert ids == {"agent-skills", "home-files"}


def test_journeys_agent_skills_profile_locks(
    ageval_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profiles = ROOT / "examples/datasets/minimal-demo/acp-profiles/profiles.acp.grok-build.agent-skills.yaml"
    if not profiles.is_file():
        pytest.skip("journeys overlay profiles were removed")
    from ageval.plugins.install import install_from_local

    install_from_local(ROOT / "plugins" / "agent-skills")
    from ageval.plugins import bootstrap as boot
    from ageval.plugins.registry import reset_global_registry

    boot._BOOTSTRAPPED = False  # type: ignore[attr-defined]
    reset_global_registry()
    env = os.environ.copy()
    env["AGEVAL_HOME"] = str(ageval_home)
    env.setdefault("XAI_API_KEY", "ci-test-key")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ageval.cli.main",
            "lock",
            str(ROOT / "examples/datasets/minimal-demo"),
            "--task",
            "terminal-jsonl-agg",
            "--profiles",
            str(ROOT / "examples/datasets/minimal-demo/acp-profiles/profiles.acp.grok-build.agent-skills.yaml"),
        ],
        cwd=ROOT,
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
    assert "agent-skills" in plugins
    assert "home-files" not in plugins
