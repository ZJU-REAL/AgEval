"""Local filesystem Package reader.

Config never imports or executes package-local Python. This adapter only
reads text files and lists top-level entries under a resolved package root.
"""

from __future__ import annotations

from pathlib import Path


class LocalPackageReader:
    """Filesystem-backed PackageReader for production composition."""

    def resolve_root(self, package_root: Path) -> Path:
        root = package_root.expanduser().resolve(strict=False)
        if not root.exists() or not root.is_dir():
            msg = f"package root is not a directory: {package_root}"
            raise FileNotFoundError(msg)
        return root

    def read_text(self, package_root: Path, relative: str) -> str:
        path = self._safe_join(package_root, relative)
        return path.read_text(encoding="utf-8")

    def exists(self, package_root: Path, relative: str) -> bool:
        try:
            path = self._safe_join(package_root, relative)
        except ValueError:
            return False
        return path.exists()

    def list_top_level(self, package_root: Path) -> list[str]:
        root = self.resolve_root(package_root)
        return sorted(entry.name for entry in root.iterdir())

    def _safe_join(self, package_root: Path, relative: str) -> Path:
        """Join a relative path and reject escapes after resolve."""
        root = self.resolve_root(package_root)
        if relative.startswith("/") or relative.startswith("\\"):
            msg = f"absolute package path not allowed: {relative}"
            raise ValueError(msg)
        candidate = (root / relative).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            msg = f"path escapes package root: {relative}"
            raise ValueError(msg) from exc
        return candidate
