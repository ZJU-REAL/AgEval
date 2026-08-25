"""on: home_overlay factory. Writes files; does not call Docker or invent PASS."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PLUGIN_ID = "home-files"
DEST_ROOTS = frozenset({"home", "workspace"})

# Same wrappers as profiles (`${NAME}`) and OpenCode (`{env:NAME}`).
# Bare `$NAME` is left for the engine (Pi interpolates apiKey itself).
_EMBEDDED_REF = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}"
    r"|\{env:([A-Za-z_][A-Za-z0-9_]*)\}"
)


class HomeFilesError(Exception):
    def __init__(self, message: str, *, kind: str = "home_files_invalid") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _safe_rel(raw: Any, *, what: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise HomeFilesError(f"{what}_required", kind="home_files_path_invalid")
    text = raw.strip().replace("\\", "/")
    if text.startswith("/") or Path(text).is_absolute():
        raise HomeFilesError(f"{what}_absolute", kind="home_files_path_invalid")
    parts = Path(text).parts
    if ".." in parts or any(p == ".." for p in parts):
        raise HomeFilesError(f"{what}_escapes", kind="home_files_path_invalid")
    if not parts:
        raise HomeFilesError(f"{what}_empty", kind="home_files_path_invalid")
    return Path(*parts)


def _reject_evaluation(dest: Path) -> None:
    if dest.parts and dest.parts[0] == "evaluation":
        raise HomeFilesError("dest_under_evaluation", kind="home_files_dest_invalid")
    if "evaluation" in dest.parts:
        raise HomeFilesError("dest_under_evaluation", kind="home_files_dest_invalid")


def _require_dir(raw: Any, *, name: str) -> Path:
    if raw is None:
        raise HomeFilesError(f"{name}_required", kind="home_files_context_missing")
    path = Path(str(raw))
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return path


def apply_files(files: Any, value: dict[str, Any]) -> None:
    if files is None:
        return
    if not isinstance(files, list):
        raise HomeFilesError("files_must_be_list", kind="home_files_options_invalid")
    package_root = _require_dir(value.get("package_root"), name="package_root")
    workspace_root = _require_dir(value.get("workspace_root"), name="workspace_root")
    cred_root = _require_dir(value.get("cred_root"), name="cred_root")
    home_overlay = cred_root / "home_overlay"
    home_overlay.mkdir(parents=True, exist_ok=True)
    environ = _overlay_environ(package_root)

    for i, item in enumerate(files):
        if not isinstance(item, dict):
            raise HomeFilesError(f"files[{i}]_not_mapping", kind="home_files_options_invalid")
        src_rel = _safe_rel(item.get("src"), what="src")
        dest_rel = _safe_rel(item.get("dest"), what="dest")
        dest_root = item.get("dest_root")
        if dest_root not in DEST_ROOTS:
            raise HomeFilesError(
                f"dest_root_invalid:{dest_root!r}",
                kind="home_files_dest_invalid",
            )
        _reject_evaluation(dest_rel)
        src = (package_root / src_rel).resolve()
        try:
            src.relative_to(package_root.resolve())
        except ValueError as exc:
            raise HomeFilesError("src_escapes_package", kind="home_files_path_invalid") from exc
        if not src.exists():
            raise HomeFilesError(f"src_missing:{src_rel}", kind="home_files_src_missing")
        root = home_overlay if dest_root == "home" else workspace_root
        dest = (root / dest_rel).resolve()
        try:
            dest.relative_to(root.resolve())
        except ValueError as exc:
            raise HomeFilesError("dest_escapes_root", kind="home_files_path_invalid") from exc
        _copy_one(src, dest, environ=environ)


def _overlay_environ(package_root: Path) -> Mapping[str, str]:
    """Same .env chain as profiles: process env, dataset root, cwd, repo root."""
    from ageval.application.host_env import load_host_env_files

    load_host_env_files(package_root=package_root)
    return os.environ


def expand_embedded_env_refs(text: str, *, environ: Mapping[str, str]) -> str:
    """Replace `${NAME}` and `{env:NAME}` from *environ*. Unset names fail closed."""
    missing: list[str] = []

    def _repl(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        raw = environ.get(name)
        if raw is None or not str(raw).strip():
            missing.append(name)
            return match.group(0)
        return str(raw).strip()

    out = _EMBEDDED_REF.sub(_repl, text)
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise HomeFilesError(
            f"overlay_env_unset:{names}",
            kind="home_files_env_unset",
        )
    return out


def _copy_one(src: Path, dest: Path, *, environ: Mapping[str, str]) -> None:
    if src.is_dir():
        if dest.exists() and dest.is_file():
            raise HomeFilesError("dest_file_src_dir", kind="home_files_dest_invalid")
        dest.mkdir(parents=True, exist_ok=True)
        src_root = src.resolve()
        for child in src.iterdir():
            try:
                child.resolve().relative_to(src_root)
            except ValueError as exc:
                raise HomeFilesError("src_symlink_escapes", kind="home_files_path_invalid") from exc
            _copy_one(child, dest / child.name, environ=environ)
        return
    if dest.exists() and dest.is_dir():
        raise HomeFilesError("dest_dir_src_file", kind="home_files_dest_invalid")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = src.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        shutil.copy2(src, dest)
        return
    if not _EMBEDDED_REF.search(text):
        shutil.copy2(src, dest)
        return
    dest.write_text(expand_embedded_env_refs(text, environ=environ), encoding="utf-8")
    shutil.copystat(src, dest)


def _files_from_ctx(ctx: Any) -> Any:
    graph = getattr(ctx, "bindings", None)
    if graph is None:
        return None
    for href in graph.chain("after_environment_ready"):
        if getattr(href, "plugin_id", None) == PLUGIN_ID and href.options:
            return dict(href.options).get("files")
    return None


async def build_home_overlay(ctx: Any, value: Any, nxt: Any) -> Any:
    """Copy declared overlay files into the box HOME or workspace."""
    files = _files_from_ctx(ctx)
    payload = dict(value) if isinstance(value, dict) else {}
    if files:
        host = ctx.host
        package_root = Path(str(ctx.dataset_root or ctx.task_root))
        environ = _overlay_environ(package_root)
        for i, item in enumerate(files):
            if not isinstance(item, Mapping):
                raise HomeFilesError(f"files[{i}]_not_mapping", kind="home_files_options_invalid")
            src_rel = _safe_rel(item.get("src"), what="src")
            dest_rel = _safe_rel(item.get("dest"), what="dest")
            dest_root = item.get("dest_root")
            if dest_root not in DEST_ROOTS:
                raise HomeFilesError(
                    f"dest_root_invalid:{dest_root!r}",
                    kind="home_files_dest_invalid",
                )
            src = (package_root / src_rel).resolve()
            if not src.exists():
                raise HomeFilesError(f"src_missing:{src_rel}", kind="home_files_src_missing")
            box_base = "/attempt/home" if dest_root == "home" else "/attempt/workspace"
            staged = Path(tempfile.mkdtemp(prefix="ageval-overlay-"))
            try:
                staged_src = staged / src.name
                _copy_one(src, staged_src, environ=environ)
                await host.upload(staged_src, f"{box_base}/{dest_rel.as_posix()}")
            finally:
                shutil.rmtree(staged, ignore_errors=True)
    return await nxt(payload)
