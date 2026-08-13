"""ACP first-party contrib: provide(executor) + image/trajectory hooks (Spec 01).

Not a full external ACP plugin package. Wrappers live here; protocol client code
may remain under ``bora.adapters.acp`` and is imported by the factory.
"""

from __future__ import annotations

from typing import Any

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
    """ExecutorSPI facade over adapters.acp.AcpExecutor."""

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
        from bora.adapters.acp import AcpExecutor

        self.profile_id = profile_id
        self._entry_id = str(entry).strip()
        self._model = model or "entry-default"
        self._base_url = base_url
        self._api_key_env = api_key
        self._inner = AcpExecutor(
            entry_id=self._entry_id,
            model=self._model,
            base_url=base_url,
            api_key_env=api_key,
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
        from bora.adapters.acp import AcpExecutor
        from bora.adapters.agent_container import wrap_docker_exec
        from bora.adapters.child_env import cli_env_for_container

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
        desc = self._inner.descriptor
        for k, v in desc.fixed_env.items():
            child_env.setdefault(str(k), str(v))
        docker_cmd = wrap_docker_exec(
            container_id=str(placement.container_id),
            uid=int(placement.uid),
            gid=int(placement.gid),
            workdir=str(getattr(placement, "workdir", None) or "/attempt/workspace"),
            env=child_env,
            argv=list(desc.acp_command),
            shared_write=bool(getattr(placement, "shared_write", False)),
            shared_gid=getattr(placement, "shared_gid", None),
        )
        bound = AcpExecutorSPI.__new__(AcpExecutorSPI)
        bound.kind = "acp"
        bound.profile_id = self.profile_id
        bound._entry_id = self._entry_id
        bound._model = self._model
        bound._base_url = self._base_url
        bound._api_key_env = self._api_key_env
        bound._inner = AcpExecutor(
            entry_id=self._entry_id,
            model=self._model,
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


__all__ = ["PLUGIN_ID", "AcpExecutorSPI", "register_acp_contrib"]
