"""ACP first-party contrib: parent client, entry registry, executor SPI.

Not an external ``plugins/acp`` package and not installed via ``bora plugin
install``. Official entries stay bake-in on ``docker/attempt``.
"""

from __future__ import annotations

from typing import Any

from bora.plugins.contrib.acp.executor import AcpExecutor
from bora.plugins.contrib.acp.resolve import resolve_acp_executor
from bora.plugins.contrib.acp.trajectory_map import acp_session_events_to_bora
from bora.plugins.contrib.acp.types import ProcessLauncher
from bora.plugins.contrib.acp.usage import normalize_acp_usage
from bora.plugins.protocol import ExecutorSPI
from bora.plugins.registry import ExtensionRegistry
from bora.plugins.slots import (
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
            from bora.plugins.errors import ExtensionMaterializeError

            raise ExtensionMaterializeError(
                "acp_entry_required",
                kind="extension_materialize_failed",
            )
        from bora.plugins.contrib.acp.executor import AcpExecutor

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

    def bind_to_target(self, placement: Any) -> AcpExecutorSPI:
        """Attach parent ACP client to the Attempt container via docker exec."""
        from bora.adapters.agent_container import wrap_docker_exec
        from bora.adapters.child_env import cli_env_for_container
        from bora.plugins.contrib.acp.executor import AcpExecutor

        child_env = cli_env_for_container(
            self._entry_id, api_key_env=self._api_key_env, base_url=self._base_url
        )
        home = str(getattr(placement, "home", None) or "/attempt/home")
        child_env["HOME"] = home
        child_env["CODEX_HOME"] = f"{home}/.codex"
        child_env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        child_env.setdefault("TERM", "xterm")
        child_env["NO_BROWSER"] = "1"
        child_env.setdefault("XDG_CONFIG_HOME", f"{home}/.config")
        child_env.setdefault("XDG_CACHE_HOME", f"{home}/.cache")
        child_env.setdefault("XDG_STATE_HOME", f"{home}/.local/state")
        child_env.setdefault("XDG_DATA_HOME", f"{home}/.local/share")
        from bora.plugins.contrib.acp.entry_local import acp_stdio_argv

        desc = self._inner.descriptor
        for k, v in desc.fixed_env.items():
            child_env.setdefault(str(k), str(v))
        docker_cmd = wrap_docker_exec(
            container_id=str(placement.container_id),
            uid=int(placement.uid),
            gid=int(placement.gid),
            workdir=str(getattr(placement, "workdir", None) or "/attempt/workspace"),
            env=child_env,
            argv=acp_stdio_argv(
                self._entry_id,
                list(desc.acp_command),
                model=self._model,
                reasoning_effort=self._reasoning_effort,
            ),
            shared_write=bool(getattr(placement, "shared_write", False)),
            shared_gid=getattr(placement, "shared_gid", None),
        )
        bound = AcpExecutorSPI.__new__(AcpExecutorSPI)
        bound.kind = "acp"
        bound.profile_id = self.profile_id
        bound._entry_id = self._entry_id
        bound._model = self._model
        bound._reasoning_effort = self._reasoning_effort
        bound._base_url = self._base_url
        bound._api_key_env = self._api_key_env
        bound._inner = AcpExecutor(
            entry_id=self._entry_id,
            model=self._model,
            reasoning_effort=self._reasoning_effort,
            descriptor=desc,
            workdir=str(getattr(placement, "workdir", None) or "/attempt/workspace"),
            api_key_env=self._api_key_env,
            base_url=self._base_url,
            command_override=docker_cmd,
        )
        return bound

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
    registry.provide(
        EXECUTOR,
        PLUGIN_ID,
        _acp_factory,
        priority=ACP_PRIORITY,
        source="first-party",
        is_default=False,
        is_factory=True,
    )
    registry.on(
        TRAJECTORY_COLLECT,
        PLUGIN_ID,
        _acp_trajectory_collect,
        priority=ACP_PRIORITY,
        source="first-party",
    )


__all__ = [
    "PLUGIN_ID",
    "AcpExecutor",
    "AcpExecutorSPI",
    "ProcessLauncher",
    "acp_session_events_to_bora",
    "normalize_acp_usage",
    "register_acp_contrib",
    "resolve_acp_executor",
]
