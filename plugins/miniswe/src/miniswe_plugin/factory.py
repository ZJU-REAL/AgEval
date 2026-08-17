"""miniswe ExecutorSPI — host mini-swe-agent loop, bash via local or docker exec."""

from __future__ import annotations

import concurrent.futures
import json
import os
import uuid
from pathlib import Path
from typing import Any

from bora.adapters.agent_contract import AgentResult, parse_validated_text_structured
from bora.plugins.errors import ExtensionMaterializeError
from miniswe_plugin import PLUGIN_ID
from miniswe_plugin.env import DockerExecEnv, LocalBashEnv
from miniswe_plugin.trajectory import to_bora_trajectory_events

_CREDENTIAL_ENV_NAMES = ("OPENAI_API_KEY", "litellm_api_key", "LITELLM_API_KEY")
_BASE_URL_ENV_FALLBACKS = ("OPENAI_BASE_URL", "litellm_base_url", "LITELLM_BASE_URL")


def describe_miniswe() -> dict[str, Any]:
    return {
        "execution_mode": "host-loop",
        "tools": "bash",
        "structured_output": "validated-text",
        "session": "one-shot",
        "stream": "none",
        "credential_env_names": _CREDENTIAL_ENV_NAMES,
        "binary": "",
    }


def _offline() -> bool:
    return os.environ.get("BORA_OFFLINE_AGENT") == "1"


def _as_positive_int(raw: Any, *, name: str, default: int) -> int:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        raise ExtensionMaterializeError(
            f"miniswe_{name}_invalid:{raw!r}",
            kind="extension_materialize_failed",
        )
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ExtensionMaterializeError(
            f"miniswe_{name}_invalid:{raw!r}",
            kind="extension_materialize_failed",
        ) from exc
    if value < 0:
        raise ExtensionMaterializeError(
            f"miniswe_{name}_invalid:{raw!r}",
            kind="extension_materialize_failed",
        )
    return value


def _as_nonneg_float(raw: Any, *, name: str, default: float) -> float:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        raise ExtensionMaterializeError(
            f"miniswe_{name}_invalid:{raw!r}",
            kind="extension_materialize_failed",
        )
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ExtensionMaterializeError(
            f"miniswe_{name}_invalid:{raw!r}",
            kind="extension_materialize_failed",
        ) from exc
    if value < 0:
        raise ExtensionMaterializeError(
            f"miniswe_{name}_invalid:{raw!r}",
            kind="extension_materialize_failed",
        )
    return value


def resolve_api_key_value(locator: str | None) -> str | None:
    names: list[str] = []
    if locator and str(locator).strip():
        names.append(str(locator).strip())
    for name in _CREDENTIAL_ENV_NAMES:
        if name not in names:
            names.append(name)
    for name in names:
        val = os.environ.get(name)
        if val and str(val).strip():
            return str(val).strip()
    return None


def resolve_base_url(explicit: str | None) -> str | None:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    for key in _BASE_URL_ENV_FALLBACKS:
        raw = os.environ.get(key)
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


def _config_search_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        import minisweagent

        roots.append(Path(minisweagent.package_dir) / "config")
        roots.append(Path(minisweagent.__file__).resolve().parent / "config")
    except Exception:
        pass
    try:
        from importlib.resources import files

        roots.append(Path(str(files("minisweagent").joinpath("config"))))
    except Exception:
        pass
    # Last resort: official mini.yaml copied into the plugin (not a BORA-authored prompt).
    roots.append(Path(__file__).resolve().parents[2] / "vendor")
    return roots


def _load_official_mini_config() -> dict[str, Any]:
    """Read official mini-swe-agent templates (installed package, then plugin vendor)."""
    try:
        import yaml
    except ImportError as exc:
        raise ExtensionMaterializeError(
            "miniswe_config_missing: PyYAML required to read official mini.yaml",
            kind="extension_materialize_failed",
        ) from exc
    names = ("mini.yaml", "default.yaml", "mini_textbased.yaml")
    tried: list[str] = []
    for root in _config_search_roots():
        for name in names:
            path = root / name
            tried.append(str(path))
            if path.is_file():
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("agent"):
                    return data
    raise ExtensionMaterializeError(
        "miniswe_config_missing: no official mini.yaml; tried " + " | ".join(tried),
        kind="extension_materialize_failed",
    )


def _write_backend_raw(collect_dir: str | None, payload: dict[str, Any]) -> None:
    if not collect_dir:
        return
    root = Path(collect_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "miniswe.json").write_text(
        json.dumps(payload, ensure_ascii=False, default=str, indent=2) + "\n",
        encoding="utf-8",
    )


class MinisweExecutorSPI:
    """Host SPI. L1 bind_to_target switches bash to docker exec; LLM stays here."""

    kind = PLUGIN_ID

    def __init__(
        self,
        *,
        options: dict[str, Any] | None = None,
        profile_id: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        plugin_id: str | None = None,
        workdir: str | None = None,
        **_kwargs: Any,
    ) -> None:
        del plugin_id
        opts = dict(options or {})
        self.options = opts
        self.profile_id = profile_id
        self.model = (model or "").strip() or "openai/gpt-4o-mini"
        self.base_url = base_url if isinstance(base_url, str) else None
        self.api_key_env = api_key if isinstance(api_key, str) else None
        self.default_workdir = str(workdir).strip() if workdir else None
        self.step_limit = _as_positive_int(opts.get("step_limit"), name="step_limit", default=30)
        self.cost_limit = _as_nonneg_float(opts.get("cost_limit"), name="cost_limit", default=0.0)
        self.cmd_timeout = _as_positive_int(opts.get("cmd_timeout"), name="cmd_timeout", default=30)
        self.session_id = f"bora-{self.profile_id or 'solver'}-{uuid.uuid4().hex[:12]}"
        self._placement: Any | None = None
        self._ready = False

    @staticmethod
    def describe() -> dict[str, Any]:
        return describe_miniswe()

    def bind_to_target(self, placement: Any) -> MinisweExecutorSPI:
        bound = MinisweExecutorSPI(
            options=self.options,
            profile_id=self.profile_id,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key_env,
            workdir=str(getattr(placement, "workdir", None) or "/attempt/workspace"),
        )
        bound._placement = placement
        bound.execution_location = "attempt-container"
        return bound

    def open(self, **kwargs: Any) -> None:
        del kwargs
        if _offline():
            raise ExtensionMaterializeError(
                "offline_forced",
                kind="extension_materialize_failed",
            )
        self._ready = True

    def close(self) -> None:
        self._ready = False

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 60.0,
        workdir: str | None = None,
        collect_dir: str | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        del redaction_sentinels
        if _offline():
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
                metadata={"plugin": PLUGIN_ID},
            )
        try:
            extra = self._run_agent(
                prompt, timeout=timeout, workdir=workdir or self.default_workdir
            )
        except ExtensionMaterializeError as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=str(getattr(exc, "message", None) or exc),
                metadata={"plugin": PLUGIN_ID},
            )
        except TimeoutError:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="miniswe_timeout",
                metadata={"plugin": PLUGIN_ID, "session_id": self.session_id},
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=f"{type(exc).__name__}:{exc}",
                metadata={"plugin": PLUGIN_ID, "session_id": self.session_id},
            )
        messages = extra.get("messages") if isinstance(extra.get("messages"), list) else []
        _write_backend_raw(collect_dir, extra)
        mapped = tuple(to_bora_trajectory_events(messages, session_id=self.session_id))
        submission = str(extra.get("submission") or extra.get("exit_content") or "")
        status = str(extra.get("exit_status") or "")
        ok = status == "Submitted"
        location = "attempt-container" if self._placement is not None else "host"
        return AgentResult(
            model=self.model,
            text=submission,
            structured=parse_validated_text_structured(submission),
            ok=ok,
            error=None if ok else (status or "miniswe_error"),
            events=mapped,
            metadata={
                "plugin": PLUGIN_ID,
                "session_id": self.session_id,
                "exit_status": status,
                "execution_location": location,
                "n_calls": extra.get("n_calls"),
                "cost": extra.get("cost"),
            },
        )

    def _make_env(self, workdir: str | None) -> LocalBashEnv | DockerExecEnv:
        cwd = str(Path(workdir or Path.cwd()).expanduser().resolve(strict=False))
        place = self._placement
        if place is None:
            return LocalBashEnv(cwd=cwd, timeout=self.cmd_timeout)
        return DockerExecEnv(
            container_id=str(place.container_id),
            uid=int(place.uid),
            gid=int(place.gid),
            workdir=str(getattr(place, "workdir", None) or "/attempt/workspace"),
            timeout=self.cmd_timeout,
        )

    def _run_agent(self, prompt: str, *, timeout: float, workdir: str | None) -> dict[str, Any]:
        try:
            from minisweagent.agents.default import DefaultAgent
            from minisweagent.models.litellm_model import LitellmModel
        except ImportError as exc:
            raise ExtensionMaterializeError(
                "miniswe_package_missing: install mini-swe-agent (uv sync --extra miniswe)",
                kind="extension_materialize_failed",
            ) from exc
        key = resolve_api_key_value(self.api_key_env)
        base = resolve_base_url(self.base_url)
        if not key and not (base and ("127.0.0.1" in base or "localhost" in base)):
            raise ExtensionMaterializeError(
                f"miniswe_missing_credential: env {self.api_key_env or 'OPENAI_API_KEY'!r} unset",
                kind="extension_materialize_failed",
            )
        model_kwargs: dict[str, Any] = {"drop_params": True}
        if key:
            model_kwargs["api_key"] = key
        if base:
            model_kwargs["api_base"] = base
        official = _load_official_mini_config()
        agent_cfg = official.get("agent") if isinstance(official.get("agent"), dict) else {}
        model_cfg = official.get("model") if isinstance(official.get("model"), dict) else {}
        obs = model_cfg.get("observation_template")
        fmt = model_cfg.get("format_error_template")
        model = LitellmModel(
            model_name=self.model,
            model_kwargs=model_kwargs,
            cost_tracking="ignore_errors",
            **({} if not obs else {"observation_template": obs}),
            **({} if not fmt else {"format_error_template": fmt}),
        )
        env = self._make_env(workdir)
        system_template = str(agent_cfg.get("system_template") or "")
        instance_template = str(agent_cfg.get("instance_template") or "")
        if not system_template or not instance_template:
            raise ExtensionMaterializeError(
                "miniswe_config_missing: official mini.yaml has no agent templates",
                kind="extension_materialize_failed",
            )
        agent = DefaultAgent(
            model,
            env,
            system_template=system_template,
            instance_template=instance_template,
            step_limit=self.step_limit,
            cost_limit=self.cost_limit,
            wall_time_limit_seconds=max(0, int(timeout)),
        )
        wait = max(1.0, float(timeout))

        def _go() -> dict[str, Any]:
            result = agent.run(prompt)
            payload = {
                "exit_status": result.get("exit_status") if isinstance(result, dict) else "",
                "submission": result.get("submission") if isinstance(result, dict) else "",
                "messages": list(agent.messages),
                "n_calls": agent.n_calls,
                "cost": agent.cost,
            }
            if isinstance(result, dict) and result.get("exit_status") == "Submitted":
                payload["exit_content"] = str(
                    result.get("submission") or result.get("content") or ""
                )
            return payload

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_go)
            try:
                return fut.result(timeout=wait)
            except concurrent.futures.TimeoutError as exc:
                raise TimeoutError("miniswe_timeout") from exc


def build_executor(**kwargs: Any) -> MinisweExecutorSPI:
    """plugin.yaml provide entry."""
    return MinisweExecutorSPI(**kwargs)
