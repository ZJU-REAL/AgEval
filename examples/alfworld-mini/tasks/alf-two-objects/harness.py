"""ALFWorld-mini harness: tiny text household world, multi-turn command loop."""

from __future__ import annotations

import re

from ageval_sdk import Agent, RunContext, RunTerminal

CMD_RE = re.compile(
    r"^\s*(look|inventory|open\s+(?P<open_r>[\w ]+)|take\s+(?P<take_o>[\w ]+)"
    r"|put\s+(?P<put_o>[\w ]+)\s+on\s+(?P<put_r>[\w ]+))\s*$",
    re.IGNORECASE,
)


class World:
    def __init__(self, spec: dict) -> None:
        self.loc = {k: str(v["at"]) for k, v in (spec.get("objects") or {}).items()}
        self.receptacles = [str(r) for r in (spec.get("receptacles") or [])]
        self.closed = {str(r) for r in (spec.get("closed") or [])}
        self.holding: list[str] = []

    def observe(self) -> str:
        parts = []
        for recep in self.receptacles:
            if recep in self.closed:
                parts.append(f"the {recep} is closed")
                continue
            here = sorted(o for o, at in self.loc.items() if at == recep)
            inside = ", ".join(f"a {o}" for o in here) if here else "nothing"
            parts.append(f"on the {recep} you see {inside}")
        inv = ", ".join(f"a {o}" for o in self.holding) if self.holding else "nothing"
        return "You look around. " + "; ".join(parts) + f". You are carrying {inv}."

    def step(self, cmd: str) -> str:
        m = CMD_RE.match(cmd)
        if not m:
            return "Nothing happens. (Unknown command.)"
        text = m.group(1).lower()
        if text == "look":
            return self.observe()
        if text == "inventory":
            inv = ", ".join(self.holding) or "nothing"
            return f"You are carrying: {inv}."
        if m.group("open_r"):
            recep = m.group("open_r").strip().lower()
            if recep in self.closed:
                self.closed.discard(recep)
                here = sorted(o for o, at in self.loc.items() if at == recep)
                inside = ", ".join(f"a {o}" for o in here) if here else "nothing"
                return f"You open the {recep}. Inside you see {inside}."
            return f"The {recep} is not something you can open here."
        if m.group("take_o"):
            obj = m.group("take_o").strip().lower()
            at = self.loc.get(obj)
            if at is None or obj in self.holding:
                return f"You don't see a {obj} you can take."
            if at in self.closed:
                return f"You can't reach the {obj}."
            self.loc[obj] = "carried"
            self.holding.append(obj)
            return f"You pick up the {obj}."
        if m.group("put_o") and m.group("put_r"):
            obj = m.group("put_o").strip().lower()
            recep = m.group("put_r").strip().lower()
            if obj not in self.holding:
                return f"You are not carrying a {obj}."
            if recep not in self.receptacles:
                return f"There is no {recep} here."
            if recep in self.closed:
                return f"The {recep} is closed."
            self.holding.remove(obj)
            self.loc[obj] = recep
            return f"You put the {obj} on the {recep}."
        return "Nothing happens."


def _extract_command(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip().strip("`>*-").strip()
        if line and CMD_RE.match(line):
            return line
    return None


async def run(ctx: RunContext) -> RunTerminal:
    goal = ctx.params.require_str("goal")
    spec = ctx.params.get("world") or {}
    max_steps = int(ctx.params.get("max_steps") or 8)
    goal_spec = {str(k): str(v) for k, v in (ctx.params.get("goal_spec") or {}).items()}
    world = World(dict(spec))
    trace: list[dict[str, str]] = []

    system = (
        "You are an agent in a text household world. Interact ONLY by replying "
        "with exactly ONE command per turn, chosen from: look | inventory | "
        "open <receptacle> | take <object> | put <object> on <receptacle>. "
        "Reply with the bare command, no punctuation, no explanation.\n"
        f"Your task: {goal}\n\n"
    )

    agent = Agent(attempt_id=ctx.scope.attempt_id)
    async with agent.session("solver", max_turns=max_steps + 2) as session:
        observation = world.observe()
        for _step in range(max_steps):
            resp = await session.invoke(system + "Current observation: " + observation)
            if not resp.get("ok"):
                return RunTerminal.failed(str(resp.get("error") or "invoke_failed"))
            reply = str(resp.get("text") or "")
            cmd = _extract_command(reply)
            if cmd is None:
                observation = "Nothing happens. Reply with exactly one bare command."
                trace.append({"reply": reply[:400], "cmd": "", "result": observation})
                continue
            result = world.step(cmd)
            trace.append({"reply": reply[:400], "cmd": cmd, "result": result})
            observation = result
            if goal_spec and all(world.loc.get(o) == d for o, d in goal_spec.items()):
                break  # goal reached — end the episode, no idle turns

    ctx.publish_json(
        "trace",
        {"goal": goal, "steps": trace, "final_locations": dict(world.loc),
         "holding": list(world.holding)},
    )
    return RunTerminal.completed("alfworld-mini")
