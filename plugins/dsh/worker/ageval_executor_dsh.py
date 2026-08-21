#!/usr/bin/env python3
"""In-container dsh worker — official DeepSeek Harness JSON-RPC SDK.

Reads one JSON object from argv[1] or stdin (no secrets required in the
payload; DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL arrive via projected env)::

    {
      "prompt": "...",
      "model": "deepseek-v4-flash",
      "provider": "deepseek-official",
      "workdir": "/attempt/workspace",
      "session_root": "/attempt/home/dsh-sessions",
      "cordis": "/opt/dsh/compositions/slim.cordis.yml",
      "session_id": "ageval-solver-…"
    }

``DSH_PERMISSION_MODE`` (when set) is forwarded into the child runtime so
``sandboxed.cordis.yml`` can resolve ``sandbox-policy.mode``.

Writes one AgentResult-shaped JSON object to stdout.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = Path("/opt/dsh")
if _PLUGIN_ROOT.is_dir() and str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

_OK_REASONS = frozenset({"completed", "max-tokens"})


def _load_trajectory() -> Any:
    try:
        from dsh_plugin import trajectory as traj
    except ImportError:
        import importlib.util

        path = Path("/opt/dsh/dsh_plugin/trajectory.py")
        if not path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("dsh_plugin_trajectory", path)
        if spec is None or spec.loader is None:
            return None
        traj = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(traj)
    return traj


def _ok_from_reason(reason: str | None, text: str) -> bool:
    if reason in {"error", "interrupted"}:
        return False
    if reason in _OK_REASONS:
        return True
    return bool(text)


def _parse_structured(text: str) -> dict[str, Any] | None:
    trimmed = text.strip()
    if not trimmed.startswith("{") or not trimmed.endswith("}"):
        return None
    try:
        val = json.loads(trimmed)
    except json.JSONDecodeError:
        return None
    return val if isinstance(val, dict) else None


def _emit(doc: dict[str, Any], *, code: int) -> int:
    print(json.dumps(doc, ensure_ascii=False, default=str))
    return code


def _read_request() -> dict[str, Any]:
    raw = sys.argv[1] if len(sys.argv) > 1 else (sys.stdin.read() or "{}")
    req = json.loads(raw)
    if not isinstance(req, dict):
        raise TypeError("request_not_object")
    return req


def main() -> int:
    try:
        req = _read_request()
    except json.JSONDecodeError as exc:
        return _emit(
            {"ok": False, "error": f"bad_request_json:{exc}", "model": "dsh", "text": ""},
            code=2,
        )
    except TypeError:
        return _emit(
            {"ok": False, "error": "request_not_object", "model": "dsh", "text": ""},
            code=2,
        )

    model = str(req.get("model") or os.environ.get("DSH_MODEL") or "deepseek-v4-flash")
    provider = str(req.get("provider") or "deepseek-official")
    prompt = str(req.get("prompt") or "")
    workdir = str(req.get("workdir") or os.environ.get("DSH_CWD") or "/attempt/workspace")
    session_root = str(
        req.get("session_root")
        or os.environ.get("DSH_SESSION_ROOT")
        or "/attempt/home/dsh-sessions"
    )
    cordis = str(
        req.get("cordis")
        or os.environ.get("DSH_CORDIS_CONFIG")
        or "/opt/dsh/compositions/slim.cordis.yml"
    )
    session_id = req.get("session_id")
    session_id_s = (
        str(session_id).strip() if isinstance(session_id, str) and session_id.strip() else None
    )

    if os.environ.get("AGEVAL_OFFLINE_AGENT") == "1":
        return _emit(
            {
                "ok": False,
                "error": "offline_forced",
                "model": model,
                "text": "",
                "metadata": {"plugin": "dsh", "execution_location": "attempt-container"},
            },
            code=1,
        )

    alias = os.environ.get("deepseek_api_key")  # noqa: SIM112 — profile locator
    if not os.environ.get("DEEPSEEK_API_KEY") and not alias:
        return _emit(
            {
                "ok": False,
                "error": "dsh_missing_credential",
                "model": model,
                "text": "",
                "metadata": {"plugin": "dsh"},
            },
            code=2,
        )

    # Alias lowercase locator so the runtime sees the official name.
    if not os.environ.get("DEEPSEEK_API_KEY") and alias:
        os.environ["DEEPSEEK_API_KEY"] = alias

    Path(session_root).mkdir(parents=True, exist_ok=True)
    Path(workdir).mkdir(parents=True, exist_ok=True)

    try:
        from deepseek_harness import DeepSeekHarness
    except ImportError as exc:
        return _emit(
            {
                "ok": False,
                "error": f"dsh_package_missing:{exc}",
                "model": model,
                "text": "",
                "metadata": {"plugin": "dsh"},
            },
            code=2,
        )

    traj = _load_trajectory()
    raw_perm = req.get("permission")
    permission = os.environ.get("DSH_PERMISSION_MODE") or (
        str(raw_perm).strip() if isinstance(raw_perm, str) else ""
    )
    child_env: dict[str, str] = {}
    if permission:
        child_env["DSH_PERMISSION_MODE"] = permission
        os.environ["DSH_PERMISSION_MODE"] = permission
    try:
        from dsh_plugin.sse_sanitize import sanitizing_base_url
    except ImportError as exc:
        return _emit(
            {
                "ok": False,
                "error": f"dsh_sanitize_missing:{exc}",
                "model": model,
                "text": "",
                "metadata": {"plugin": "dsh"},
            },
            code=2,
        )
    harness_kwargs: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "cwd": workdir,
        "session_root": session_root,
        "cordis": cordis,
        "env": child_env,
    }
    raw_tokens = req.get("max_tokens")
    if raw_tokens is not None:
        try:
            tokens = int(raw_tokens)
        except (TypeError, ValueError):
            tokens = 0
        if tokens <= 0:
            return _emit(
                {
                    "ok": False,
                    "error": f"dsh_max_tokens_invalid:{raw_tokens!r}",
                    "model": model,
                    "text": "",
                    "metadata": {"plugin": "dsh"},
                },
                code=2,
            )
        harness_kwargs["max_tokens"] = tokens
    try:
        with (
            sanitizing_base_url(),
            DeepSeekHarness(**harness_kwargs) as harness,
        ):
            session = harness.start_session(session_id_s)
            result = session.run(prompt)
        native = [e for e in (result.events or []) if isinstance(e, dict)]
        mapped: list[dict[str, Any]] = []
        usage = None
        if traj is not None:
            mapped = traj.to_ageval_trajectory_events(native, session_id=result.session_id)
            usage = traj.extract_usage(native)
        text = str(result.final_response or "")
        reason = result.finish_reason
        ok = _ok_from_reason(reason, text)
        return _emit(
            {
                "model": model,
                "text": text,
                "structured": _parse_structured(text),
                "ok": ok,
                "error": None if ok else str(reason or "dsh_error"),
                "events": mapped,
                "native_events": native,
                "usage": usage,
                "metadata": {
                    "plugin": "dsh",
                    "execution_location": "attempt-container",
                    "session_id": result.session_id,
                    "finish_reason": reason,
                    "session_root": result.session_root or session_root,
                    "composition": str(
                        req.get("composition") or Path(cordis).name.removesuffix(".cordis.yml")
                    ),
                    "permission": permission or None,
                },
            },
            code=0 if ok else 1,
        )
    except Exception as exc:  # noqa: BLE001
        return _emit(
            {
                "model": model,
                "text": "",
                "structured": None,
                "ok": False,
                "error": f"{type(exc).__name__}:{exc}",
                "metadata": {
                    "plugin": "dsh",
                    "execution_location": "attempt-container",
                },
            },
            code=1,
        )


if __name__ == "__main__":
    raise SystemExit(main())
