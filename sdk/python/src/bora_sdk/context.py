"""HarnessContext and parameter view (HC-1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RunScope:
    """Logical run scope visible to Harness (no host secrets)."""

    attempt_id: str
    trial_id: str
    run_id: str
    deadline_monotonic: float | None = None


class HarnessParameterView:
    """Read-only parameter projection (JSON-compatible)."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = MappingProxyType(dict(data))

    def get(self, path: str, default: Any = None) -> Any:
        cur: Any = self._data
        for part in path.split("."):
            if not isinstance(cur, Mapping) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def require_int(self, path: str) -> int:
        val = self.get(path)
        if not isinstance(val, int) or isinstance(val, bool):
            raise KeyError(path)
        return val

    def require_str(self, path: str) -> str:
        val = self.get(path)
        if not isinstance(val, str):
            raise KeyError(path)
        return val

    def as_mapping(self) -> Mapping[str, Any]:
        return self._data


@dataclass
class HarnessContext:
    """Minimal HC-1 context injected into ``async def run(ctx)``."""

    params: HarnessParameterView
    scope: RunScope
    workspace_root: Path
    artifact_dir: Path
    _closed: bool = False
    _published: dict[str, Path] | None = None

    def __post_init__(self) -> None:
        if self._published is None:
            self._published = {}

    def close(self) -> None:
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    def publish_json(self, artifact_id: str, data: Mapping[str, Any]) -> Path:
        """Write declared JSON artifact under artifact_dir (Harness-local)."""
        import json

        if self._closed:
            raise RuntimeError("context closed")
        path = self.artifact_dir / f"{artifact_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        path.write_text(payload + "\n", encoding="utf-8")
        assert self._published is not None
        self._published[artifact_id] = path
        return path

    def publish_file(self, artifact_id: str, source: Path) -> Path:
        if self._closed:
            raise RuntimeError("context closed")
        dest = self.artifact_dir / source.name
        dest.write_bytes(source.read_bytes())
        assert self._published is not None
        self._published[artifact_id] = dest
        return dest
