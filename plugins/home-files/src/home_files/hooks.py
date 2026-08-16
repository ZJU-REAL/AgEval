"""on: home_overlay factory. Writes files; does not call Docker or invent PASS."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

PLUGIN_ID = "home-files"
DEST_ROOTS = frozenset({"home", "workspace"})


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
        _copy_one(src, dest)


def _copy_one(src: Path, dest: Path) -> None:
    if src.is_dir():
        if dest.exists() and dest.is_file():
            raise HomeFilesError("dest_file_src_dir", kind="home_files_dest_invalid")
        dest.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            _copy_one(child, dest / child.name)
        return
    if dest.exists() and dest.is_dir():
        raise HomeFilesError("dest_dir_src_file", kind="home_files_dest_invalid")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def build_home_overlay(**kwargs: Any) -> Any:
    options = dict(kwargs.get("options") or {})
    files = options.get("files")

    async def handler(ctx: Any, value: Any, nxt: Any) -> Any:
        del ctx
        payload = dict(value) if isinstance(value, dict) else {}
        apply_files(files, payload)
        return await nxt(payload)

    return handler
