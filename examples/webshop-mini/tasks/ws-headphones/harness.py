"""WebShop-mini harness: simulated shop, search/click/select/buy loop."""

from __future__ import annotations

import re

from bora_sdk import Agent, HarnessContext, HarnessTerminal

CMD_RE = re.compile(
    r"^\s*(search\s+(?P<q>.+)|click\s+(?P<item>[a-z0-9_-]+)"
    r"|select\s+(?P<otype>[\w-]+)\s+(?P<oval>[\w. -]+)|back|buy)\s*$",
    re.IGNORECASE,
)


class Shop:
    def __init__(self, catalog: list[dict]) -> None:
        self.catalog = {str(p["id"]): p for p in catalog}
        self.results: list[str] = []
        self.current: str | None = None
        self.selected: dict[str, str] = {}
        self.purchase: dict | None = None

    def search(self, query: str) -> str:
        terms = [t for t in re.split(r"[^a-z0-9.]+", query.lower()) if t]
        scored = []
        for pid, p in self.catalog.items():
            hay = (p["title"] + " " + " ".join(p.get("attributes", []))).lower()
            score = sum(1 for t in terms if t in hay)
            if score:
                scored.append((score, pid))
        scored.sort(key=lambda x: (-x[0], x[1]))
        self.results = [pid for _, pid in scored[:5]]
        self.current = None
        self.selected = {}
        if not self.results:
            return "No results. Try different keywords."
        lines = ["Results:"]
        for pid in self.results:
            p = self.catalog[pid]
            lines.append(f"  [{pid}] {p['title']} — ${p['price']:.2f}")
        return "\n".join(lines)

    def click(self, pid: str) -> str:
        if pid not in self.catalog or (self.results and pid not in self.results):
            return f"No item [{pid}] on this page."
        self.current = pid
        self.selected = {}
        p = self.catalog[pid]
        lines = [f"Item [{pid}] {p['title']} — ${p['price']:.2f}"]
        lines.append("  attributes: " + ", ".join(p.get("attributes", [])))
        for otype, vals in (p.get("options") or {}).items():
            lines.append(f"  option {otype}: " + " | ".join(vals))
        lines.append("Use: select <option> <value>, buy, or back.")
        return "\n".join(lines)

    def select(self, otype: str, oval: str) -> str:
        if self.current is None:
            return "Open an item first (click <id>)."
        opts = self.catalog[self.current].get("options") or {}
        if otype not in opts:
            return f"No option {otype!r} for this item."
        match = next((v for v in opts[otype] if v.lower() == oval.lower().strip()), None)
        if match is None:
            return f"Value {oval!r} not available for {otype}."
        self.selected[otype] = match
        return f"Selected {otype} = {match}."

    def back(self) -> str:
        self.current = None
        self.selected = {}
        if not self.results:
            return "Search results are empty. Use search <keywords>."
        lines = ["Results:"]
        for pid in self.results:
            p = self.catalog[pid]
            lines.append(f"  [{pid}] {p['title']} — ${p['price']:.2f}")
        return "\n".join(lines)

    def buy(self) -> str:
        if self.current is None:
            return "Open an item first (click <id>)."
        p = self.catalog[self.current]
        self.purchase = {
            "item_id": self.current,
            "title": p["title"],
            "price": p["price"],
            "attributes": list(p.get("attributes", [])),
            "options": dict(self.selected),
        }
        return f"Purchased [{self.current}] {p['title']} for ${p['price']:.2f}."

    def step(self, cmd: str) -> str:
        m = CMD_RE.match(cmd)
        if not m:
            return "Nothing happens. (Unknown command.)"
        if m.group("q"):
            return self.search(m.group("q"))
        if m.group("item"):
            return self.click(m.group("item").lower())
        if m.group("otype"):
            return self.select(m.group("otype").lower(), m.group("oval"))
        head = cmd.strip().split()[0].lower()
        if head == "back":
            return self.back()
        if head == "buy":
            return self.buy()
        return "Nothing happens."


def _extract_command(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip().strip("`>*-").strip()
        if line and CMD_RE.match(line):
            return line
    return None


async def run(ctx: HarnessContext) -> HarnessTerminal:
    instruction = ctx.params.require_str("instruction")
    catalog = ctx.params.get("catalog") or []
    max_steps = int(ctx.params.get("max_steps") or 12)
    shop = Shop(list(catalog))
    trace: list[dict[str, str]] = []

    system = (
        "You are shopping in a text web shop. Interact ONLY by replying with "
        "exactly ONE command per turn: search <keywords> | click <item_id> | "
        "select <option> <value> | back | buy. Select all required options "
        "BEFORE buying. Reply with the bare command only.\n"
        f"Shopping instruction: {instruction}\n\n"
    )

    agent = Agent(attempt_id=ctx.scope.attempt_id)
    observation = "Welcome. Start with: search <keywords>."
    async with agent.session("solver", max_turns=max_steps + 2) as session:
        for _step in range(max_steps):
            resp = await session.invoke(system + "Current page:\n" + observation)
            if not resp.get("ok"):
                return HarnessTerminal.failed(str(resp.get("error") or "invoke_failed"))
            reply = str(resp.get("text") or "")
            cmd = _extract_command(reply)
            if cmd is None:
                observation = "Nothing happens. Reply with exactly one bare command."
                trace.append({"reply": reply[:400], "cmd": "", "result": observation})
                continue
            result = shop.step(cmd)
            trace.append({"reply": reply[:400], "cmd": cmd, "result": result[:400]})
            observation = result
            if shop.purchase is not None:
                break  # episode ends at buy — no idle turns (eval finding #5)

    ctx.publish_json(
        "purchase",
        {"instruction": instruction, "purchase": shop.purchase, "steps": trace,
         "n_steps": len(trace)},
    )
    return HarnessTerminal.completed("webshop-mini")
