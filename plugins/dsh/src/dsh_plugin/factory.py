"""dsh ExecutorSPI — official DeepSeek Harness JSON-RPC SDK (not ACP).

Drive ``deepseek-harness-sdk`` / ``dsh-jsonrpc-agent``. Model is passed on
``initialize``. Credentials arrive as projected env (locator name on the
profile). Host SPI is Recognition / L0 only; L1 Ready uses bind_to_target.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from bora.adapters.agent_contract import AgentResult, parse_validated_text_structured
from bora.plugins.errors import ExtensionMaterializeError
from dsh_plugin import PLUGIN_ID
from dsh_plugin.trajectory import extract_usage, to_bora_trajectory_events

DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_PROVIDER = "deepseek-official"
DEFAULT_COMPOSITION = "slim"
_CREDENTIAL_ENV_NAMES = ("DEEPSEEK_API_KEY", "deepseek_api_key")
_BASE_URL_ENV_FALLBACKS = ("DEEPSEEK_BASE_URL", "deepseek_base_url")
_OK_REASONS = frozenset({"completed", "max-tokens"})


def describe_dsh() -> dict[str, Any]:
    return {
        "execution_mode": "container-worker",
        "tools": "native",
        "structured_output": "validated-text",
        "session": "reuse-process",
        "stream": "native-events",
        "credential_env_names": _CREDENTIAL_ENV_NAMES,
        "binary": "dsh-jsonrpc-agent",
    }


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_composition_path(name: str | None) -> Path:
    slug = (name or DEFAULT_COMPOSITION).strip() or DEFAULT_COMPOSITION
    if "/" in slug or "\\" in slug or slug.startswith("."):
        raise ExtensionMaterializeError(
            f"dsh_composition_invalid:{slug}",
            kind="extension_materialize_failed",
        )
    path = _plugin_root() / "compositions" / f"{slug}.cordis.yml"
    if not path.is_file():
        raise ExtensionMaterializeError(
            f"dsh_composition_missing:{slug}",
            kind="extension_materialize_failed",
        )
    return path


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


def _write_backend_raw(
    collect_dir: str | None,
    native: list[dict[str, Any]],
    notifications: list[dict[str, Any]] | None = None,
) -> None:
    if not collect_dir:
        return
    root = Path(collect_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows = list(native)
    if notifications:
        rows.extend(notifications)
    if not rows:
        return
    (root / "dsh_events.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in rows) + "\n",
        encoding="utf-8",
    )


def _offline() -> bool:
    return os.environ.get("BORA_OFFLINE_AGENT") == "1"


def _ok_from_reason(reason: str | None, text: str) -> bool:
    if reason in {"error", "interrupted"}:
        return False
    if reason in _OK_REASONS:
        return True
    return bool(text)


class DshExecutorSPI:
    """Host SPI wrapping DeepSeekHarness. L1 uses DshContainerExecutor."""

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
        **_kwargs: Any,
    ) -> None:
        del plugin_id
        opts = dict(options or {})
        self.options = opts
        self.profile_id = profile_id
        self.model = (model or "").strip() or DEFAULT_MODEL
        self.provider = str(opts.get("provider") or DEFAULT_PROVIDER).strip() or DEFAULT_PROVIDER
        self.composition = str(opts.get("composition") or DEFAULT_COMPOSITION).strip() or (
            DEFAULT_COMPOSITION
        )
        self.base_url = base_url
        self.api_key_env = api_key
        self.default_workdir = str(opts.get("_workdir")).strip() if opts.get("_workdir") else None
        self._harness: Any = None
        self._session: Any = None
        self._session_id = f"bora-{self.profile_id or 'solver'}-{uuid.uuid4().hex[:12]}"
        self._session_root: str | None = None
        self._tmp_session: tempfile.TemporaryDirectory[str] | None = None
        self._ready = False

    @staticmethod
    def describe() -> dict[str, Any]:
        return describe_dsh()

    def bind_to_target(self, placement: Any) -> Any:
        from dsh_plugin.container import DshContainerExecutor

        workdir = str(getattr(placement, "workdir", None) or "/attempt/workspace")
        home = str(getattr(placement, "home", None) or "/attempt/home")
        return DshContainerExecutor(
            container_id=str(placement.container_id),
            uid=int(placement.uid),
            gid=int(placement.gid),
            workdir_container=workdir,
            home_container=home,
            model=self.model,
            provider=self.provider,
            composition=self.composition,
            base_url=self.base_url if isinstance(self.base_url, str) else None,
            api_key_env=self.api_key_env if isinstance(self.api_key_env, str) else None,
            session_id=self._session_id,
        )

    def open(self, **kwargs: Any) -> None:
        del kwargs
        if _offline():
            raise ExtensionMaterializeError(
                "offline_forced",
                kind="extension_materialize_failed",
            )
        self._ready = True

    def close(self) -> None:
        harness = self._harness
        self._harness = None
        self._session = None
        self._ready = False
        if harness is not None:
            with contextlib.suppress(Exception):
                harness.close()
        tmp = self._tmp_session
        self._tmp_session = None
        if tmp is not None:
            tmp.cleanup()

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
            self._ensure_started(workdir or self.default_workdir)
        except ExtensionMaterializeError as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=str(getattr(exc, "message", None) or exc),
                metadata={"plugin": PLUGIN_ID},
            )
        assert self._session is not None
        try:
            result = self._run_session(prompt, timeout=timeout)
        except TimeoutError:
            self.close()
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="dsh_timeout",
                metadata={"plugin": PLUGIN_ID, "session_id": self._session_id},
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=f"{type(exc).__name__}:{exc}",
                metadata={"plugin": PLUGIN_ID, "session_id": self._session_id},
            )
        native = [e for e in (result.events or []) if isinstance(e, dict)]
        notes: list[dict[str, Any]] = []
        for note in result.notifications or ():
            payload = getattr(note, "payload", None)
            method = getattr(note, "method", None)
            if isinstance(payload, dict):
                notes.append({"method": method, **payload})
        _write_backend_raw(collect_dir, native, notes)
        mapped = tuple(to_bora_trajectory_events(native, session_id=result.session_id))
        text = str(result.final_response or "")
        reason = result.finish_reason
        ok = _ok_from_reason(reason, text)
        return AgentResult(
            model=self.model,
            text=text,
            structured=parse_validated_text_structured(text),
            ok=ok,
            error=None if ok else str(reason or "dsh_error"),
            events=mapped,
            usage=extract_usage(native),
            metadata={
                "plugin": PLUGIN_ID,
                "session_id": result.session_id,
                "finish_reason": reason,
                "session_root": result.session_root or self._session_root,
                "composition": self.composition,
                "execution_location": "host",
            },
        )

    def _run_session(self, prompt: str, *, timeout: float) -> Any:
        assert self._session is not None
        wait = max(1.0, float(timeout))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(self._session.run, prompt)
            try:
                return fut.result(timeout=wait)
            except concurrent.futures.TimeoutError as exc:
                raise TimeoutError("dsh_timeout") from exc

    def _ensure_started(self, workdir: str | None) -> None:
        if self._harness is not None:
            return
        try:
            from deepseek_harness import DeepSeekHarness
        except ImportError as exc:
            raise ExtensionMaterializeError(
                "dsh_package_missing: install deepseek-harness-sdk==0.1.0rc6 "
                "(uv sync --extra dsh / pip install deepseek-harness-sdk==0.1.0rc6)",
                kind="extension_materialize_failed",
            ) from exc
        key = resolve_api_key_value(self.api_key_env if isinstance(self.api_key_env, str) else None)
        base = resolve_base_url(self.base_url if isinstance(self.base_url, str) else None)
        if not key and not (base and ("127.0.0.1" in base or "localhost" in base)):
            raise ExtensionMaterializeError(
                f"dsh_missing_credential: env {self.api_key_env or 'DEEPSEEK_API_KEY'!r} unset",
                kind="extension_materialize_failed",
            )
        cordis = resolve_composition_path(self.composition)
        cwd = str(Path(workdir or Path.cwd()).expanduser().resolve(strict=False))
        if self._session_root is None:
            self._tmp_session = tempfile.TemporaryDirectory(prefix="bora-dsh-")
            self._session_root = self._tmp_session.name
        env: dict[str, str] = {}
        if key:
            env["DEEPSEEK_API_KEY"] = key
        if base:
            env["DEEPSEEK_BASE_URL"] = base
        self._harness = DeepSeekHarness(
            provider=self.provider,
            model=self.model,
            cwd=cwd,
            session_root=self._session_root,
            cordis=str(cordis),
            env=env,
        )
        self._harness.start()
        self._session = self._harness.start_session(self._session_id)
        self._ready = True


def build_executor(**kwargs: Any) -> DshExecutorSPI:
    """plugin.yaml provide entry: factory(**kwargs) -> ExecutorSPI."""
    return DshExecutorSPI(**kwargs)
