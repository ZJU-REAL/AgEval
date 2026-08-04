"""Deterministic ToolSet + CallLimit package."""

from __future__ import annotations

from bora_sdk import HarnessContext, HarnessTerminal, Tool, ToolSet


async def run(ctx: HarnessContext) -> HarnessTerminal:
    limit = int(ctx.params.get("call_limit", 2))
    mode = str(ctx.params.get("mode", "success"))
    hooks: list[str] = []
    ts = ToolSet(call_limit=limit, allowlist={"echo"})
    ts.before_hooks.append(lambda n, a: hooks.append(f"before:{n}"))
    ts.after_hooks.append(lambda n, o: hooks.append(f"after:{n}"))

    def echo(args: dict) -> str:
        return str(args.get("text", ""))

    ts.add(Tool(name="echo", fn=echo))
    observations = []
    observations.append(await ts.call("echo", {"text": "a"}))
    observations.append(await ts.call("echo", {"text": "b"}))
    if mode == "denied":
        observations.append(await ts.call("echo", {"text": "c"}))  # should deny
    ctx.publish_json(
        "tool-trace",
        {
            "observations": observations,
            "hooks": hooks,
            "side_effect_counter": ts.side_effect_counter,
            "mode": mode,
        },
    )
    return HarnessTerminal.completed("sdk-tool-guard")
