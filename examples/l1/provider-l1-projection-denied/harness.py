"""Stub harness — L1 orchestrator handles projection probe for docker kind."""
from bora_sdk import HarnessContext, HarnessTerminal
async def run(ctx: HarnessContext) -> HarnessTerminal:
    return HarnessTerminal.failed("use_l1_orchestrator")
