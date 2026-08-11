#!/usr/bin/env python3
"""In-container nooa worker (stdlib only).

Reads one JSON object from stdin::

    {
      "prompt": "...",
      "agent": "lib.agents:JsonlAggAgent",
      "method": "run",
      "package_root": "/attempt/package",
      "workdir": "/attempt/workspace"
    }

Writes one AgentResult-shaped JSON object to stdout. Does **not** import host
``bora`` packages — package-local agents under package_root only.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any


def _load_agent(agent_ref: str, package_root: Path) -> Any:
    if ":" in agent_ref:
        mod_name, cls_name = agent_ref.split(":", 1)
    else:
        mod_name, cls_name = agent_ref, None
    root_s = str(package_root)
    if package_root.is_dir() and root_s not in sys.path:
        sys.path.insert(0, root_s)
    mod = importlib.import_module(mod_name)
    if not cls_name:
        return mod
    cls = getattr(mod, cls_name, None)
    if cls is None:
        raise RuntimeError(f"nooa_agent_class_missing:{cls_name}")
    return cls() if callable(cls) else cls


def _to_result(raw: Any, *, agent_ref: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return {
            "model": "nooa",
            "text": str(raw.get("text") or ""),
            "structured": raw.get("structured")
            if isinstance(raw.get("structured"), dict)
            else (raw if raw.get("structured") is None and "ok" in raw else raw.get("structured")),
            "ok": bool(raw.get("ok", True)),
            "error": str(raw["error"]) if raw.get("error") else None,
            "metadata": {
                "plugin": "nooa",
                "agent": agent_ref,
                "execution_location": "attempt-container",
            },
        }
    text = str(raw) if raw is not None else ""
    return {
        "model": "nooa",
        "text": text,
        "structured": None,
        "ok": True,
        "error": None,
        "metadata": {
            "plugin": "nooa",
            "agent": agent_ref,
            "execution_location": "attempt-container",
        },
    }


def main() -> int:
    try:
        req = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"bad_request_json:{exc}", "model": "nooa", "text": ""}))
        return 2
    if not isinstance(req, dict):
        print(json.dumps({"ok": False, "error": "request_not_object", "model": "nooa", "text": ""}))
        return 2

    agent_ref = str(req.get("agent") or "").strip()
    method_name = str(req.get("method") or "run").strip() or "run"
    prompt = str(req.get("prompt") or "")
    package_root = Path(str(req.get("package_root") or "/attempt/package")).expanduser()
    workdir = str(req.get("workdir") or "/attempt/workspace")

    if not agent_ref:
        print(json.dumps({"ok": False, "error": "nooa_options_agent_required", "model": "nooa", "text": ""}))
        return 2

    try:
        agent = _load_agent(agent_ref, package_root)
        method = getattr(agent, method_name, None)
        if method is None or not callable(method):
            raise RuntimeError(f"nooa_method_missing:{method_name}")
        try:
            raw = method(prompt, workdir=workdir)
        except TypeError:
            raw = method(prompt)
        out = _to_result(raw, agent_ref=agent_ref)
        # structured fallback: if ok dict without structured, use whole payload
        if out.get("structured") is None and isinstance(raw, dict) and "ok" in raw:
            structured = {k: v for k, v in raw.items() if k not in {"ok", "error", "text"}}
            if structured:
                out["structured"] = structured
        print(json.dumps(out, ensure_ascii=False))
        return 0 if out.get("ok") else 1
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "model": "nooa",
                    "text": "",
                    "structured": None,
                    "ok": False,
                    "error": f"{type(exc).__name__}:{exc}",
                    "metadata": {
                        "plugin": "nooa",
                        "agent": agent_ref,
                        "execution_location": "attempt-container",
                    },
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
