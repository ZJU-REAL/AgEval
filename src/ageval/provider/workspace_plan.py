"""Workspace plan validation for L0 Provider."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ageval.provider.errors import ERROR_INVALID_WORKDIR, ProviderError
from ageval.runtime.identity import AttemptIdentity


@dataclass(frozen=True, slots=True)
class WorkspacePlan:
    """Provider-owned Attempt workspace under a validated base directory."""

    attempt: AttemptIdentity
    # Base directory that will contain the Attempt workdir (must already exist).
    base_dir: Path
    # Relative workdir name under base_dir (no escapes).
    relative_workdir: str = "workspace"

    def resolve_workdir(self) -> Path:
        """Return the canonical workdir path; reject escapes."""
        base = self.base_dir.expanduser().resolve(strict=False)
        if not base.exists() or not base.is_dir():
            raise ProviderError(
                ERROR_INVALID_WORKDIR,
                f"base_dir is not a directory: {self.base_dir}",
            )
        rel = self.relative_workdir.replace("\\", "/").strip("/")
        if not rel or ".." in Path(rel).parts or rel.startswith("/"):
            raise ProviderError(
                ERROR_INVALID_WORKDIR,
                f"invalid relative workdir: {self.relative_workdir!r}",
            )
        workdir = (base / rel).resolve(strict=False)
        try:
            workdir.relative_to(base)
        except ValueError as exc:
            raise ProviderError(
                ERROR_INVALID_WORKDIR,
                f"workdir escapes base_dir: {self.relative_workdir}",
            ) from exc
        return workdir
