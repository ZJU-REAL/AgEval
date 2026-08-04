"""Config-owned ports (protocols). Concrete adapters live under ``bora.adapters``."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class PackageReader(Protocol):
    """Narrow read-only port used by Config Core.

    Adapters implement this protocol; Config must not depend on filesystem details.
    """

    def resolve_root(self, package_root: Path) -> Path:
        """Resolve and validate that *package_root* is an existing directory."""
        ...

    def read_text(self, package_root: Path, relative: str) -> str:
        """Read a UTF-8 text file relative to the package root."""
        ...

    def exists(self, package_root: Path, relative: str) -> bool:
        """Return True if a package-relative path exists."""
        ...

    def list_top_level(self, package_root: Path) -> list[str]:
        """List top-level names (files and directories) under the package root."""
        ...
