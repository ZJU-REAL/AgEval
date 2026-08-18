"""on: home_overlay factory. Expands dests; copy is home-files.apply_files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from home_files.hooks import apply_files

PLUGIN_ID = "agent-skills"
DEST_ROOTS = frozenset({"home", "workspace"})
KNOWN_ACP_ENTRIES = frozenset({"codex", "claude-code", "opencode", "pi", "grok-build"})

# Always-on generic dests, then per-entry extras. grok-build has no extra prefix.
_SKILL_PREFIX: dict[str, dict[str, str]] = {
    "_always": {"home": ".agents/skills", "workspace": ".agents/skills"},
    "codex": {"home": ".codex/skills", "workspace": ".codex/skills"},
    "claude-code": {"home": ".claude/skills", "workspace": ".claude/skills"},
    "opencode": {"home": ".config/opencode/skills", "workspace": ".opencode/skills"},
    "pi": {"home": ".pi/agent/skills", "workspace": ".pi/skills"},
}


class AgentSkillsError(Exception):
    def __init__(self, message: str, *, kind: str = "agent_skills_invalid") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _dest_roots(raw: Any) -> list[str]:
    if raw is None:
        return ["home"]
    if not isinstance(raw, list) or not raw:
        raise AgentSkillsError("dest_roots_invalid", kind="agent_skills_options_invalid")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item not in DEST_ROOTS:
            raise AgentSkillsError(
                f"dest_root_invalid:{item!r}",
                kind="agent_skills_options_invalid",
            )
        root = str(item)
        if root not in seen:
            seen.add(root)
            out.append(root)
    return out


def _require_src(raw: Any, *, what: str) -> str:
    if not isinstance(raw, dict):
        raise AgentSkillsError(f"{what}_not_mapping", kind="agent_skills_options_invalid")
    src = raw.get("src")
    if not isinstance(src, str) or not src.strip():
        raise AgentSkillsError(f"{what}_src_required", kind="agent_skills_path_invalid")
    if raw.get("dest") is not None:
        raise AgentSkillsError(f"{what}_dest_not_allowed", kind="agent_skills_options_invalid")
    return src.strip().replace("\\", "/")


def _acp_entries(value: dict[str, Any]) -> list[str]:
    raw = value.get("acp_entries")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AgentSkillsError("acp_entries_invalid", kind="agent_skills_context_missing")
    out: list[str] = []
    for item in raw:
        entry = str(item).strip()
        if not entry:
            continue
        if entry not in KNOWN_ACP_ENTRIES:
            raise AgentSkillsError(
                f"unknown_acp_entry:{entry}",
                kind="agent_skills_entry_invalid",
            )
        if entry not in out:
            out.append(entry)
    return out


def _add(
    files: list[dict[str, str]],
    seen: set[tuple[str, str]],
    *,
    src: str,
    dest: str,
    dest_root: str,
) -> None:
    key = (dest_root, dest)
    if key in seen:
        return
    seen.add(key)
    files.append({"src": src, "dest": dest, "dest_root": dest_root})


def expand_files(options: dict[str, Any], value: dict[str, Any]) -> list[dict[str, str]]:
    """Turn skills/instructions into home-files rows. Dedup dests."""
    dest_roots = _dest_roots(options.get("dest_roots"))
    entries = _acp_entries(value)
    files: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    skills = options.get("skills")
    if skills is None:
        skills = []
    if not isinstance(skills, list):
        raise AgentSkillsError("skills_must_be_list", kind="agent_skills_options_invalid")
    prefixes = [_SKILL_PREFIX["_always"]]
    for entry in entries:
        extra = _SKILL_PREFIX.get(entry)
        if extra is not None:
            prefixes.append(extra)
    for i, row in enumerate(skills):
        src = _require_src(row, what=f"skills[{i}]")
        name = Path(src).name
        if not name or name in {".", ".."}:
            raise AgentSkillsError("skill_name_invalid", kind="agent_skills_path_invalid")
        for dest_root in dest_roots:
            for prefix_map in prefixes:
                prefix = prefix_map[dest_root]
                _add(
                    files,
                    seen,
                    src=src,
                    dest=f"{prefix}/{name}",
                    dest_root=dest_root,
                )

    instructions = options.get("instructions")
    if instructions is None:
        instructions = []
    if not isinstance(instructions, list):
        raise AgentSkillsError("instructions_must_be_list", kind="agent_skills_options_invalid")
    for i, row in enumerate(instructions):
        src = _require_src(row, what=f"instructions[{i}]")
        fname = Path(src).name
        if fname == "AGENTS.md":
            # Instruction exception: always workspace-root AGENTS.md.
            _add(files, seen, src=src, dest="AGENTS.md", dest_root="workspace")
            if "codex" in entries and "home" in dest_roots:
                _add(files, seen, src=src, dest=".codex/AGENTS.md", dest_root="home")
        elif fname == "CLAUDE.md":
            if "claude-code" not in entries:
                continue
            if "home" in dest_roots:
                _add(files, seen, src=src, dest=".claude/CLAUDE.md", dest_root="home")
            _add(files, seen, src=src, dest="CLAUDE.md", dest_root="workspace")
        else:
            raise AgentSkillsError(
                f"instruction_unsupported:{fname}",
                kind="agent_skills_options_invalid",
            )
    return files


def _assert_skill_markdown(files: list[dict[str, str]], value: dict[str, Any]) -> None:
    package_raw = value.get("package_root")
    if package_raw is None:
        raise AgentSkillsError("package_root_required", kind="agent_skills_context_missing")
    package_root = Path(str(package_raw))
    checked: set[str] = set()
    for row in files:
        src = row["src"]
        if src in checked:
            continue
        checked.add(src)
        folder = package_root / Path(*Path(src).parts)
        if not folder.is_dir():
            continue
        if not (folder / "SKILL.md").is_file():
            raise AgentSkillsError(
                f"skill_md_missing:{src}",
                kind="agent_skills_skill_invalid",
            )


def build_home_overlay(**kwargs: Any) -> Any:
    options = dict(kwargs.get("options") or {})

    async def handler(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        payload = dict(value) if isinstance(value, dict) else {}
        files = expand_files(options, payload)
        _assert_skill_markdown(files, payload)
        apply_files(files, payload)
        return await nxt(payload)

    return handler
