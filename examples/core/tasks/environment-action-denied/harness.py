"""Public expected-failure: Runtime denied undeclared env action before mutation."""

from __future__ import annotations

import json
from pathlib import Path

from ageval_sdk import HarnessContext, HarnessTerminal


async def run(ctx: HarnessContext) -> HarnessTerminal:
    meta_path = Path.cwd() / ".ageval_env_result.json"
    if not meta_path.is_file():
        meta_path = Path(__file__).resolve().parent / ".ageval_env_result.json"
    if not meta_path.is_file():
        return HarnessTerminal.failed("environment_result_missing")

    env = json.loads(meta_path.read_text(encoding="utf-8"))
    if not env.get("ok"):
        return HarnessTerminal.failed(env.get("error") or "environment_failed")

    probe = env.get("deny_probe") if isinstance(env.get("deny_probe"), dict) else {}
    if not probe.get("denied_before_mutation"):
        return HarnessTerminal.failed("expected_runtime_deny_probe_missing")

    unknown = probe.get("unknown_action") if isinstance(probe.get("unknown_action"), dict) else {}
    dangerous = probe.get("dangerous_sql") if isinstance(probe.get("dangerous_sql"), dict) else {}
    ctx.publish_json(
        "deny-output",
        {
            "denied_before_mutation": True,
            "mutation_executed": False,
            "unknown_action_error": unknown.get("error"),
            "dangerous_sql_error": dangerous.get("error"),
            "error": "environment_action_denied",
            "container": env.get("container"),
        },
    )
    return HarnessTerminal.completed("environment-action-denied")
