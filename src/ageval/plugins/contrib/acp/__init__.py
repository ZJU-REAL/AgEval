"""ACP first-party contrib: parent client, entry registry, executor SPI.

Not an external ``plugins/acp`` package and not installed via ``ageval plugin
install``. Official entries stay bake-in on ``docker/attempt``.
"""

from __future__ import annotations

from typing import Any

from ageval.plugins.contrib.acp.executor import AcpExecutor
from ageval.plugins.contrib.acp.hooks import ENSURE_RUNTIME_PRIORITY, ensure_runtime
from ageval.plugins.contrib.acp.trajectory_map import acp_session_events_to_ageval
from ageval.plugins.contrib.acp.types import ProcessLauncher
from ageval.plugins.contrib.acp.usage import normalize_acp_usage
from ageval.plugins.protocol import ExecutorSPI, InjectRequirement
from ageval.plugins.registry import ExtensionRegistry
from ageval.plugins.slots import (
    AFTER_ENVIRONMENT_READY,
    ENVIRONMENT,
    EXECUTOR,
    TRAJECTORY_COLLECT,
)

PLUGIN_ID = "acp"
# Stronger than default multi (1000); weaker than explicit profile binding.
ACP_PRIORITY = 100


class AcpExecutorSPI(ExecutorSPI):
    """ExecutorSPI facade over the in-plugin AcpExecutor."""

    kind = "acp"

    def __init__(
        self,
        *,
        options: dict[str, Any] | None = None,
        profile_id: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        plugin_id: str | None = None,
        home: str | None = None,
        **_kwargs: Any,
    ) -> None:
        del plugin_id
        opts = dict(options or {})
        entry = opts.get("entry") or opts.get("entry_id")
        if not entry or not str(entry).strip():
            from ageval.plugins.errors import ExtensionMaterializeError

            raise ExtensionMaterializeError(
                "acp_entry_required",
                kind="extension_materialize_failed",
            )
        from ageval.plugins.contrib.acp.executor import AcpExecutor

        self.profile_id = profile_id
        self._entry_id = str(entry).strip()
        self._model = model or "entry-default"
        self._reasoning_effort = _optional_str(opts.get("reasoning_effort"))
        self._base_url = base_url
        self._api_key_env = api_key
        extra_env: dict[str, str] | None = None
        if home and str(home).strip():
            home_s = str(home).strip()
            extra_env = {
                "HOME": home_s,
                "CODEX_HOME": f"{home_s}/.codex",
                "XDG_CONFIG_HOME": f"{home_s}/.config",
                "XDG_CACHE_HOME": f"{home_s}/.cache",
                "XDG_STATE_HOME": f"{home_s}/.local/state",
                "XDG_DATA_HOME": f"{home_s}/.local/share",
            }
            # Engines hard-fail when a pointed-to dir is missing (codex exits 1
            # on absent CODEX_HOME); the attempt home exists but subdirs don't.
            import contextlib
            from pathlib import Path

            for sub in (".codex", ".config", ".cache", ".local/state", ".local/share"):
                with contextlib.suppress(OSError):
                    Path(home_s, sub).mkdir(parents=True, exist_ok=True)
        workdir = _kwargs.get("workdir")
        workdir_s = str(workdir).strip() if workdir else None
        self._inner = AcpExecutor(
            entry_id=self._entry_id,
            model=self._model,
            reasoning_effort=self._reasoning_effort,
            base_url=base_url,
            api_key_env=api_key,
            workdir=workdir_s or None,
            env=extra_env,
        )

    @staticmethod
    def describe() -> dict[str, Any]:
        return {
            "execution_mode": "acp-stdio",
            "tools": "native",
            "structured_output": "validated-text",
            "session": "new-only",
            "stream": "native-events",
            "credential_env_names": (),
            "binary": "",
        }

    def open(self, **kwargs: Any) -> None:
        del kwargs

    def close(self) -> None:
        if hasattr(self._inner, "close"):
            self._inner.close()

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> Any:
        return self._inner.invoke(
            prompt,
            timeout=timeout,
            workdir=workdir,
            collect_dir=collect_dir,
            redaction_sentinels=redaction_sentinels,
        )


def _optional_str(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _acp_factory(**kwargs: Any) -> AcpExecutorSPI:
    return AcpExecutorSPI(**kwargs)


async def _acp_trajectory_collect(ctx: Any, value: Any, nxt: Any) -> Any:
    """Tag trajectory payload as ACP-sourced; seal path writes from chain output (#71 B)."""
    out = await nxt(value)
    if isinstance(out, dict):
        meta = dict(out.get("metadata") or {})
        meta.setdefault("trajectory_source", "acp")
        return {**out, "metadata": meta}
    return out


def register_acp_contrib(registry: ExtensionRegistry) -> None:
    registry.exclusive(
        EXECUTOR,
        PLUGIN_ID,
        _acp_factory,
        priority=ACP_PRIORITY,
        source="first-party",
        is_factory=True,
    )
    registry.chain(
        AFTER_ENVIRONMENT_READY,
        PLUGIN_ID,
        ensure_runtime,
        priority=ENSURE_RUNTIME_PRIORITY,
        source="first-party",
        is_factory=True,
    )
    registry.chain(
        TRAJECTORY_COLLECT,
        PLUGIN_ID,
        _acp_trajectory_collect,
        priority=ACP_PRIORITY,
        source="first-party",
    )
    # The pipe always comes from the box, so the box must be able to attach one.
    registry.declare_inject(
        PLUGIN_ID,
        (InjectRequirement(service=ENVIRONMENT, capabilities=("attach_stdio",)),),
    )


__all__ = [
    "PLUGIN_ID",
    "AcpExecutor",
    "AcpExecutorSPI",
    "ProcessLauncher",
    "acp_session_events_to_ageval",
    "ensure_runtime",
    "normalize_acp_usage",
    "register_acp_contrib",
]
